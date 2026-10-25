"""Optional, pinned SmolLM2 adapter. Imports heavy dependencies only on use."""
import hashlib
import json
from pathlib import Path

MODEL_ID = 'HuggingFaceTB/SmolLM2-135M-Instruct'
REVISION = '12fd25f77366fa6b3b4b768ec3050bf629380bac'
HASHES = {
    'config.json': '8eb740e8bbe4cff95ea7b4588d17a2432deb16e8075bc5828ff7ba9be94d982a',
    'model.safetensors': '5af571cbf074e6d21a03528d2330792e532ca608f24ac70a143f6b369968ab8c',
}


def verify_model(directory):
    directory = Path(directory)
    for name, expected in HASHES.items():
        digest = hashlib.sha256()
        with (directory / name).open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f'pinned model hash mismatch: {name}')
    return dict(HASHES)


def check_runtime():
    import torch
    import transformers
    if torch.__version__.split('+')[0] != '2.5.1' or transformers.__version__ != '4.46.3':
        raise ValueError('adapter requires torch 2.5.1 and transformers 4.46.3')


def load_reference(directory):
    import torch
    from transformers import LlamaForCausalLM
    check_runtime()
    verify_model(directory)
    model = LlamaForCausalLM.from_pretrained(str(directory), local_files_only=True,
        trust_remote_code=False, use_safetensors=True, torch_dtype=torch.float32,
        attn_implementation='eager')
    return model.eval()


class Partition:
    """Exactly 15 of 30 decoder layers, CPU float32, full sequence, no KV cache.

    Stage 0 owns embeddings and layers 0..14. Stage 1 owns layers 15..29,
    final RMS norm and the tied output-head weights. Each process loads only
    its own tensors from the shared safetensors file. Batch size is fixed to 1.
    """
    def __init__(self, directory, stage):
        import torch
        from safetensors import safe_open
        from transformers import LlamaConfig
        from transformers.models.llama.modeling_llama import LlamaDecoderLayer, LlamaRMSNorm, LlamaRotaryEmbedding
        check_runtime()
        verify_model(directory)
        if type(stage) is not int or stage not in (0, 1):
            raise ValueError('stage must be 0 or 1')
        self.stage = stage
        config = LlamaConfig.from_dict(json.loads((Path(directory) / 'config.json').read_text()))
        config._attn_implementation = 'eager'
        self.layers = []
        with safe_open(str(Path(directory) / 'model.safetensors'), framework='pt', device='cpu') as weights:
            keys = list(weights.keys())
            for index in range(stage * 15, (stage + 1) * 15):
                with torch.device('meta'):
                    layer = LlamaDecoderLayer(config, index)
                prefix = f'model.layers.{index}.'
                state = {key[len(prefix):]: weights.get_tensor(key).float() for key in keys if key.startswith(prefix)}
                layer.load_state_dict(state, strict=True, assign=True)
                self.layers.append(layer.eval())
            with torch.device('meta'):
                if stage == 0:
                    self.embedding = torch.nn.Embedding(config.vocab_size, config.hidden_size)
                else:
                    self.norm = LlamaRMSNorm(config.hidden_size, eps=config.rms_norm_eps)
                    self.head = torch.nn.Linear(config.hidden_size, config.vocab_size, bias=False)
            if stage == 0:
                self.embedding.load_state_dict({'weight': weights.get_tensor('model.embed_tokens.weight').float()}, assign=True)
            else:
                self.norm.load_state_dict({'weight': weights.get_tensor('model.norm.weight').float()}, assign=True)
                # This pinned checkpoint ties the output head to token embeddings.
                self.head.load_state_dict({'weight': weights.get_tensor('model.embed_tokens.weight').float()}, assign=True)
        self.rotary = LlamaRotaryEmbedding(config=config).eval()

    def __call__(self, value):
        import torch
        if self.stage == 0:
            if value.dtype != torch.int64 or value.ndim != 2 or value.shape[0] != 1 or not 1 <= value.shape[1] <= 64:
                raise ValueError('stage 0 requires int64 [1, 1..64] token IDs')
            if value.min() < 0 or value.max() >= 49152:
                raise ValueError('token ID out of range')
            hidden = self.embedding(value)
        else:
            if value.dtype != torch.float32 or value.ndim != 3 or value.shape[0] != 1 or value.shape[2] != 576 or not 1 <= value.shape[1] <= 64:
                raise ValueError('stage 1 requires float32 [1, 1..64, 576] activations')
            if not torch.isfinite(value).all():
                raise ValueError('non-finite activation')
            hidden = value
        length = hidden.shape[1]
        cache_position = torch.arange(length, device='cpu')
        position_ids = cache_position.unsqueeze(0)
        # Full, unpadded causal sequence: position j may attend only to 0..j.
        mask = torch.full((length, length), torch.finfo(torch.float32).min)
        mask = torch.triu(mask, diagonal=1)[None, None, :, :]
        position_embeddings = self.rotary(hidden, position_ids)
        for layer in self.layers:
            hidden = layer(hidden, attention_mask=mask, position_ids=position_ids,
                           past_key_value=None, output_attentions=False, use_cache=False,
                           cache_position=cache_position, position_embeddings=position_embeddings)[0]
        if self.stage == 1:
            hidden = self.head(self.norm(hidden[:, -1:, :]))[:, 0, :]
        return hidden
