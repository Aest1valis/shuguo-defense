import unittest
from tracker import TargetTracker

def observation(state,k=0):
    return dict(id=k,state=state,x=100,y=200,good_probability=.95)

class TrackerTests(unittest.TestCase):
    def test_retry_until_acknowledgement_and_do_not_repeat_hit(self):
        t=TargetTracker();a=t.observe([observation('good')],0)[0];t.clicked(a,0)
        self.assertEqual(t.observe([observation('good')],.03),[])
        a=t.observe([observation('good')],.07)[0];t.clicked(a,.07)
        t.observe([observation('hit')],.10);t.observe([observation('hit')],.12)
        self.assertEqual(t.confirmed,1)
        self.assertEqual(t.observe([observation('good')],.14),[])
        for n in range(3):t.observe([observation('empty')],.20+n*.03)
        self.assertEqual(len(t.observe([observation('good')],.31)),1)

    def test_bomb_remains_blocked_through_ambiguous_frames(self):
        t=TargetTracker();self.assertEqual(t.observe([observation('bomb')],0),[])
        for n in range(1,5):self.assertEqual(t.observe([observation('good')],n*.02),[])
        for n in range(3):t.observe([observation('empty')],.20+n*.03)
        self.assertEqual(len(t.observe([observation('good')],.30)),1)

    def test_disappearance_is_not_a_claim_of_success(self):
        t=TargetTracker();a=t.observe([observation('good')],0)[0];t.clicked(a,0)
        for n in range(3):t.observe([observation('empty')],.1+n*.03)
        self.assertEqual(t.confirmed,0);self.assertEqual(t.unverified,1)

    def test_oldest_unacknowledged_target_goes_first(self):
        t=TargetTracker();t.observe([observation('good',2)],0)
        actions=t.observe([observation('good',0),observation('good',2)],.02)
        self.assertEqual([a['id'] for a in actions],[2,0])

if __name__=='__main__':unittest.main()
