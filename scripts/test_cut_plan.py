"""关键编辑条件回归，使用合成区间，不读取私人录音。"""
import copy
import unittest

from cut_plan import merge_ranges, validate_plan


def base_plan():
    return {'schema_version':1,'source_id':'synthetic','source_sha256':'1'*64,'duration_seconds':5,
        'deletions':[{'id':'d1','start':1,'end':1.1,'reason':'填充'},
            {'id':'d2','start':1.6,'end':1.7,'reason':'填充'}],
        'speech_units':[{'id':'middle-word','start':1.2,'end':1.5,'action':'keep'}]}


class PlanTests(unittest.TestCase):
    def test_keeps_word_between_deletions(self):
        r = validate_plan(base_plan(),merge_gap=0)
        self.assertEqual(r['final_deletions'],[[1.,1.1],[1.6,1.7]])
        self.assertAlmostEqual(r['expected_output_seconds'],4.8)
        self.assertEqual(r['keep_segments'][1],[1.1,1.6])

    def test_merge_cannot_expand_even_without_asr(self):
        p = base_plan()
        p['speech_units'] = []
        with self.assertRaisesRegex(ValueError,'额外区间'):
            validate_plan(p,merge_gap=1)

    def test_checks_already_merged_final_range(self):
        p = base_plan()
        p['deletions'] = [{'id':'old-merged','start':1,'end':1.7,'reason':'旧清单'}]
        with self.assertRaisesRegex(ValueError,'保留字词'):
            validate_plan(p,merge_gap=0)

    def test_overlap_and_touch_merge_without_extra(self):
        p = base_plan()
        p['speech_units'] = []
        p['deletions'] = [{'id':str(i),'start':a,'end':b,'reason':'已决定'}
            for i,(a,b) in enumerate([(1,1.2),(1.1,1.4),(1.4,1.5)])]
        r = validate_plan(p,merge_gap=0)
        self.assertEqual(r['final_deletions'],[[1.,1.5]])
        self.assertAlmostEqual(r['deleted_seconds'],.5)

    def test_short_filler_not_dropped(self):
        p = base_plan()
        p['deletions'] = [{'id':'short','start':2,'end':2.04,'reason':'短填充'}]
        r = validate_plan(p,merge_gap=0)
        self.assertAlmostEqual(r['deleted_seconds'],.04)

    def test_pending_public_content_preserved(self):
        p = base_plan()
        p['deletions'][0]['execute'] = False
        r = validate_plan(p,merge_gap=0)
        self.assertAlmostEqual(r['deleted_seconds'],.1)
        self.assertEqual(len(r['pending_deletions']),1)
        self.assertEqual(r['keep_segments'][0],[0.,1.6])

    def test_unknown_response_protected(self):
        for action in ['keep','unknown']:
            p = base_plan()
            p['speech_units'] = [{'id':'response','start':1.01,'end':1.09,'action':action}]
            with self.subTest(action=action),self.assertRaises(ValueError):
                validate_plan(p,merge_gap=0)

    def test_decided_filler_can_be_deleted(self):
        p = base_plan()
        p['speech_units'].append({'id':'filler','start':1.01,'end':1.09,'action':'delete'})
        self.assertTrue(validate_plan(p,merge_gap=0)['final_range_protection_passed'])

    def test_rejects_invalid_time_and_identity(self):
        for value in [float('nan'),float('inf'),-1,6,True]:
            p = base_plan()
            p['deletions'][0]['start'] = value
            with self.subTest(value=value),self.assertRaises(ValueError):
                validate_plan(p,merge_gap=0)
        for key,value in [('source_sha256','wrong'),('duration_seconds',0),('speech_units',None)]:
            p = base_plan()
            p[key] = value
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_plan(p,merge_gap=0)

    def test_timeline_conserves_every_kept_interval(self):
        p = base_plan()
        p['deletions'] = [{'id':'first','start':0,'end':.2,'reason':'准备'},
            {'id':'last','start':4.8,'end':5,'reason':'结束'}]
        r = validate_plan(p,merge_gap=0)
        self.assertEqual(r['timeline'][0]['source_start'],.2)
        self.assertAlmostEqual(r['timeline'][-1]['output_end'],4.6)
        self.assertAlmostEqual(r['deleted_seconds']+r['expected_output_seconds'],5)

    def test_no_cuts_and_empty_result(self):
        p = base_plan()
        p['deletions'] = []
        self.assertEqual(validate_plan(p,merge_gap=0)['keep_segments'],[[0.,5.]])
        p['deletions'] = [{'id':'all','start':0,'end':5,'reason':'错误'}]
        p['speech_units'] = []
        with self.assertRaisesRegex(ValueError,'全部音频'):
            validate_plan(p,merge_gap=0)

    def test_merge_argument_must_be_explicit(self):
        with self.assertRaises(TypeError):
            merge_ranges([[1,2]])


if __name__ == '__main__':
    unittest.main(verbosity=2)
