"""Issue 7: predict 10-point action chunks for the Gazebo-only adapter patch."""

import base64
import json
import sys
from pathlib import Path

import torch
from safetensors.torch import load_file, load_model
from transformers.initialization import no_init_weights

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'learning'))

import check_checkpoint
import run_policy


def main():
    case = Path(sys.argv[1])
    condition = json.loads((case / 'case.json').read_text())
    original_load = check_checkpoint.load_checkpoint
    torch.manual_seed(1000)

    def load(path, contract=None, device='cpu'):
        print('LOADING_STRICT_WEIGHTS', flush=True)
        with no_init_weights():
            policy, preprocessor, postprocessor = original_load(path, contract, device)
        policy.config.n_action_steps = 10
        policy.reset()
        if condition['stage'] == 'before':
            policy.to('cpu')
            if condition['model'] == 'pi05':
                weights = load_file(condition['base_weights'], device='cpu')
                fixed = policy._fix_pytorch_state_dict_keys(weights, policy.config)
                mapped = {key if key.startswith('model.') else 'model.' + key: value
                          for key, value in fixed.items()}
                policy.load_state_dict(mapped, strict=True)
                del weights, fixed, mapped
            else:
                load_model(policy, condition['base_weights'], strict=True, device='cpu')
            policy.to(device)
            policy.eval()
            policy.reset()
        (case / 'model-loaded.json').write_text(json.dumps({
            'stage': condition['stage'],
            'strict_load': True,
            'normalization': 'saved train processors',
        }))
        print('MODEL_LOADED', flush=True)
        return policy, preprocessor, postprocessor

    def action(observation, contract, loaded):
        policy, preprocessor, postprocessor = loaded
        raw = base64.b64decode(observation['rgb'], validate=True)
        image = torch.frombuffer(bytearray(raw), dtype=torch.uint8).reshape(*contract['image_shape_hwc'])
        batch = {
            contract['image_key']: image.permute(2, 0, 1).float() / 255,
            contract['state_key']: torch.tensor(observation['state'], dtype=torch.float32),
            'task': contract['task'],
        }
        with torch.inference_mode():
            result = postprocessor(policy.predict_action_chunk(preprocessor(batch)))[:, :10, :]
        if tuple(result.shape) != (1, 10, 8) or not torch.isfinite(result).all():
            raise ValueError('expected finite (1,10,8) chunk')
        values = result[0].cpu().tolist()
        with (case / 'actions.jsonl').open('a') as stream:
            stream.write(json.dumps({
                'id': observation['id'],
                'state': observation['state'],
                'action': values,
                'stamp_ns': observation['state_stamp_ns'],
            }) + '\n')
        return values

    check_checkpoint.load_checkpoint = load
    run_policy.policy_action = action
    sys.argv = [
        'run_policy.py', '--mode', 'checkpoint', '--checkpoint', condition['checkpoint'],
        '--device', 'cuda', '--port', str(condition.get('port', 9197)), '--steps', '50',
        '--timeout', '30',
    ]
    run_policy.main()


if __name__ == '__main__':
    main()
