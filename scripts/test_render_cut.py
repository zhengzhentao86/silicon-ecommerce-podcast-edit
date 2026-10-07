"""两个不同合成音频的实际FFmpeg无损剪切与拒绝行为回归。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf

from render_cut import file_hash, render


SR = 48000


def fixture(root, *, channels=2, duration=1.4):
    t = np.arange(round(duration*SR))/SR
    audio = (.14*np.sin(2*np.pi*310*t)).astype('float32')
    if channels==2:
        audio = np.column_stack([audio,.11*np.sin(2*np.pi*640*t)]).astype('float32')
    source = root/'source.wav'
    sf.write(source,audio,SR,subtype='FLOAT')
    plan = {'schema_version':1,'source_id':'synthetic-audio','source_sha256':file_hash(source),
        'duration_seconds':len(audio)/SR,'deletions':[{'id':'d1','start':.4,'end':.5,'reason':'合成填充'},
            {'id':'d2','start':.8,'end':.86,'reason':'合成停顿'}],
        'speech_units':[{'id':'kept','start':.5,'end':.8,'action':'keep'}]}
    return source,audio,plan


class RenderTests(unittest.TestCase):
    def check_audio(self, *, channels, duration):
        with tempfile.TemporaryDirectory(prefix='podcast-skill-test-') as td:
            root = Path(td)
            source,raw,plan = fixture(root,channels=channels,duration=duration)
            output = root/'result.wav'
            record = render(source,plan,output,merge_gap=0)
            result,sr = sf.read(output,dtype='float32',always_2d=True)
            raw = raw[:,None] if raw.ndim==1 else raw
            self.assertEqual(sr,SR)
            self.assertEqual(result.shape[1],channels)
            self.assertAlmostEqual(len(result)/SR,duration-.16,places=5)
            self.assertAlmostEqual(float(np.max(np.abs(result))),float(np.max(np.abs(raw))),places=5)
            # 排除接口渐变后，各保留区间必须逐样本匹配，无意外下混或增益。
            for m in record['timeline']:
                a,b = round(m['source_start']*SR),round(m['source_end']*SR)
                c,d = round(m['output_start']*SR),round(m['output_end']*SR)
                np.testing.assert_allclose(result[c+240:d-240],raw[a+240:b-240],atol=1e-7)
            self.assertEqual(record['source_sha256'],file_hash(source))
            self.assertEqual(record['output_sha256'],file_hash(output))
            self.assertEqual(json.loads(output.with_suffix('.timeline.json').read_text())['channels'],channels)

    def test_stereo_preserves_separate_channels(self):
        self.check_audio(channels=2,duration=1.4)

    def test_another_mono_source_with_different_length(self):
        self.check_audio(channels=1,duration=1.8)

    def test_identity_merge_and_word_fail_before_output(self):
        for kind in ['hash','merge','word','duration']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as td:
                root = Path(td)
                source,raw,plan = fixture(root)
                gap = 0
                if kind=='hash':
                    plan['source_sha256'] = '0'*64
                elif kind=='merge':
                    gap = 1
                elif kind=='word':
                    plan['deletions'] = [{'id':'bad','start':.4,'end':.86,'reason':'旧错误合并'}]
                else:
                    plan['duration_seconds'] = 10
                out = root/'bad.wav'
                with self.assertRaises(ValueError):
                    render(source,plan,out,merge_gap=gap)
                self.assertFalse(out.exists())
                self.assertFalse(out.with_suffix('.timeline.json').exists())

    def test_existing_version_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source,raw,plan = fixture(root)
            out = root/'existing.wav'
            out.write_bytes(b'existing-version')
            with self.assertRaisesRegex(ValueError,'已存在'):
                render(source,plan,out,merge_gap=0)
            self.assertEqual(out.read_bytes(),b'existing-version')

    def test_cli_plan_and_actual_render(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source,raw,plan = fixture(root)
            path = root/'plan.json'
            path.write_text(json.dumps(plan))
            scripts = Path(__file__).resolve().parent
            validated,output = root/'validated.json',root/'cli.wav'
            for command in [
                [sys.executable,str(scripts/'cut_plan.py'),'--plan',str(path),'--output',str(validated),'--merge-gap','0'],
                [sys.executable,str(scripts/'render_cut.py'),'--source',str(source),'--plan',str(path),'--output',str(output),'--merge-gap','0']]:
                subprocess.run(command,check=True,capture_output=True,text=True)
            self.assertTrue(json.loads(validated.read_text())['final_range_protection_passed'])
            self.assertAlmostEqual(sf.info(output).duration,1.24,places=5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
