"""从已审读清单导出无损干声，源指纹和最终字音保护在渲染前复核。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

import numpy as np
import soundfile as sf

from cut_plan import validate_plan


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def render(source, plan, output, *, merge_gap, fade_ms=4.0):
    source, output = Path(source), Path(output)
    checked = validate_plan(plan, merge_gap=merge_gap)
    if not math.isfinite(fade_ms) or not 0 <= fade_ms <= 20:
        raise ValueError('剪口渐变需为0至20毫秒，不能用长渐变掩盖字音错切')
    sidecar = output.with_suffix('.timeline.json')
    if output.suffix.lower() != '.wav':
        raise ValueError('无损干声输出应为WAV，最终编码另行执行')
    if output.exists() or sidecar.exists():
        raise ValueError('输出或时间映射已存在，请指定新版本路径')
    if file_hash(source) != checked['source_sha256']:
        raise ValueError('输入文件指纹不符，拒绝套用其他源的时间戳')
    probe = subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=channels','-of','json',str(source)],
        check=True, capture_output=True, text=True)
    streams = json.loads(probe.stdout).get('streams', [])
    if not streams or streams[0]['channels'] not in (1,2):
        raise ValueError('当前无损导出只支持单/双声道；多声道需先显式决定处理方式')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='podcast-cut-', dir=output.parent) as td:
        temp = Path(td)
        decoded, rendered = temp/'source.wav', temp/'rendered.wav'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(source),'-map','0:a:0',
            '-ar','48000','-c:a','pcm_f32le','-rf64','auto',str(decoded)], check=True)
        mappings, cursor, peak = [], 0, 0.0
        with sf.SoundFile(decoded) as src, sf.SoundFile(rendered, mode='w', samplerate=src.samplerate,
                channels=src.channels, subtype='FLOAT') as dst:
            sr = src.samplerate
            decoded_duration = len(src)/sr
            if abs(decoded_duration-checked['source_duration_seconds']) > .08:
                raise ValueError('实际解码时长与清单不符，需重建源时间轴')
            for a,b in checked['keep_segments']:
                first,last = round(a*sr), min(round(b*sr), len(src))
                length = last-first
                if length <= 0:
                    raise ValueError('存在不足一个采样点的保留段，需重审剪口')
                src.seek(first)
                fade = min(round(fade_ms/1000*sr), length//2)
                consumed = 0
                while consumed < length:
                    data = src.read(min(sr,length-consumed), dtype='float32', always_2d=True)
                    if not len(data):
                        raise ValueError('源读取不足，不能交付不完整模块')
                    if fade:
                        indices = consumed+np.arange(len(data))
                        gain = np.minimum(np.minimum(indices/max(1,fade-1),
                            (length-1-indices)/max(1,fade-1)),1.0)
                        data *= np.maximum(gain,0)[:,None]
                    peak = max(peak,float(np.max(np.abs(data))))
                    if not np.all(np.isfinite(data)) or peak>1.0:
                        raise ValueError('FLOAT输入出现非有限值或过载，需回到声音处理阶段')
                    dst.write(data)
                    consumed += len(data)
                mappings.append({'source_start':first/sr,'source_end':last/sr,
                    'output_start':cursor/sr,'output_end':(cursor+length)/sr})
                cursor += length
        with sf.SoundFile(rendered) as f:
            assert len(f)==cursor
            assert f.channels==streams[0]['channels']
        if abs(cursor/sr-checked['expected_output_seconds']) > .08+len(mappings)/sr:
            raise ValueError('导出时长不符合清单')
        if file_hash(source) != checked['source_sha256']:
            raise ValueError('导出期间源文件变化，拒绝交付')
        record = {'source_id':checked['source_id'],'source_sha256':checked['source_sha256'],
            'source_decoded_duration_seconds':decoded_duration,'output':str(output.resolve()),
            'output_duration_seconds':cursor/sr,'output_sha256':file_hash(rendered),
            'sample_rate':sr,'channels':streams[0]['channels'],'sample_peak':peak,
            'fade_ms':fade_ms,'timeline':mappings,'cut_protection_passed':True,
            'scope':'无损干声及已输入字音保护；未做BGM、响度或人工听校'}
        report = temp/'timeline.json'
        report.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        # 输出预检和结尾复检；不覆盖已有版本。
        if output.exists() or sidecar.exists():
            raise ValueError('导出目标在处理期间出现，请换新路径')
        os.link(rendered, output)
        try:
            os.link(report, sidecar)
        except OSError:
            output.unlink()
            raise
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--merge-gap', type=float, required=True)
    parser.add_argument('--fade-ms', type=float, default=4.0)
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding='utf-8'))
        record = render(args.source, plan, args.output, merge_gap=args.merge_gap, fade_ms=args.fade_ms)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(json.dumps({k:record[k] for k in ['output','output_duration_seconds','channels','sample_peak','cut_protection_passed']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
