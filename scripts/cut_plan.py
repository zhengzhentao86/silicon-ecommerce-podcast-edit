"""校验原音编辑决定，合并后再次保护保留字音；不执行语义判断。"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

EPS = 1e-9


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label}必须是有限数值')
    return float(value)


def interval(row, duration, label):
    a = number(row.get('start'), label+' start')
    b = number(row.get('end'), label+' end')
    if not 0 <= a < b <= duration:
        raise ValueError(f'{label}区间必须在源时长内且start小于end')
    return a, b


def merge_ranges(rows, *, gap_threshold):
    """关键参数无默认值，调用方必须明确传入。"""
    result = []
    for a, b in sorted(rows):
        if result and a <= result[-1][1]+gap_threshold:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a, b])
    return result


def range_difference(rows, allowed):
    extra = []
    for start, end in rows:
        cursor = start
        for a, b in allowed:
            if b <= cursor or a >= end:
                continue
            if a > cursor+EPS:
                extra.append([cursor, min(a, end)])
            cursor = max(cursor, min(b, end))
        if cursor < end-EPS:
            extra.append([cursor, end])
    return extra


def validate_plan(plan, *, merge_gap):
    if not isinstance(plan, dict) or plan.get('schema_version') != 1:
        raise ValueError('需要schema_version=1的编辑清单')
    if not isinstance(plan.get('source_id'), str) or not plan['source_id'].strip():
        raise ValueError('缺少源素材source_id')
    digest = plan.get('source_sha256', '')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
        raise ValueError('source_sha256必须是实际输入文件的64位SHA-256')
    duration = number(plan.get('duration_seconds'), 'duration_seconds')
    if duration <= 0:
        raise ValueError('源时长必须大于0')
    gap = number(merge_gap, 'merge_gap')
    if gap < 0:
        raise ValueError('合并间隔不能为负数')
    tolerance = number(plan.get('protection_tolerance_seconds', .003), '字音容差')
    if not 0 <= tolerance <= .02:
        raise ValueError('字音容差必须在0至0.02秒内；定位不足时应保留候选')
    rows, units = plan.get('deletions'), plan.get('speech_units')
    if not isinstance(rows, list) or not isinstance(units, list):
        raise ValueError('deletions和speech_units必须提供列表；还须独立核对转录覆盖')
    decided, pending, seen = [], [], set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError('删除条目必须是对象')
        key = row.get('id')
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError('删除条目id必须非空且唯一')
        seen.add(key)
        a, b = interval(row, duration, f'删除{i}')
        if not isinstance(row.get('reason'), str) or not row['reason'].strip():
            raise ValueError(f'删除{key}缺少判断理由')
        execute = row.get('execute', True)
        if not isinstance(execute, bool):
            raise ValueError('execute必须是布尔值')
        if execute:
            decided.append([a, b])
        else:
            pending.append(row)
    allowed = merge_ranges(decided, gap_threshold=0.0)
    final = merge_ranges(decided, gap_threshold=gap)
    extra = range_difference(final, allowed)
    if extra:
        raise ValueError(f'合并产生未决定删除的额外区间：{extra[:3]}；请用显式merge-gap 0')
    protected, seen = [], set()
    for i, unit in enumerate(units):
        if not isinstance(unit, dict):
            raise ValueError('字词单元必须是对象')
        key = unit.get('id')
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError('字词单元id必须非空且唯一')
        seen.add(key)
        a, b = interval(unit, duration, f'字词{i}')
        action = unit.get('action', 'keep')
        if action not in {'keep', 'delete', 'unknown'}:
            raise ValueError(f'未知字词action：{action}')
        if action != 'delete':
            protected.append((a, b, key))
    cut_index = 0
    for a, b, key in sorted(protected):
        while cut_index < len(final) and final[cut_index][1] <= a:
            cut_index += 1
        j = cut_index
        while j < len(final) and final[j][0] < b:
            overlap = min(b, final[j][1])-max(a, final[j][0])
            if overlap > tolerance+EPS:
                raise ValueError(f'最终删除覆盖保留字词{key}约{overlap:.6f}秒；需收缩或取消剪口')
            j += 1
    keep, cursor = [], 0.0
    for a, b in final:
        if a > cursor:
            keep.append([cursor, a])
        cursor = max(cursor, b)
    if cursor < duration:
        keep.append([cursor, duration])
    if not keep:
        raise ValueError('清单将删除全部音频；不能导出空模块')
    timeline, output_cursor = [], 0.0
    for a, b in keep:
        timeline.append({'source_start':a, 'source_end':b, 'output_start':output_cursor, 'output_end':output_cursor+b-a})
        output_cursor += b-a
    return {'schema_version':1, 'source_id':plan['source_id'], 'source_sha256':digest.lower(),
        'input_plan':plan, 'merge_gap_seconds':gap, 'final_deletions':final,
        'keep_segments':keep, 'timeline':timeline, 'pending_deletions':pending,
        'source_duration_seconds':duration, 'expected_output_seconds':output_cursor,
        'deleted_seconds':duration-output_cursor, 'protected_units_checked':len(protected),
        'final_range_protection_passed':True, 'extra_deleted_ranges':extra,
        'protection_scope':'只保护已输入单元与已决定区间；须另外核对转录覆盖、边界和原意'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--merge-gap', type=float, required=True)
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding='utf-8'))
        result = validate_plan(plan, merge_gap=args.merge_gap)
        if args.output.resolve() == args.plan.resolve():
            raise ValueError('验证输出不能覆盖源编辑清单')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({k:result[k] for k in ['source_id','deleted_seconds','expected_output_seconds','protected_units_checked','final_range_protection_passed']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
