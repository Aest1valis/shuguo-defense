from pathlib import Path
from PIL import Image
import threading,unittest
from unittest.mock import patch
import numpy as np
from results import ResultReader,StableResult

ROOT=Path(__file__).parent
def picture(name='result_test.png'):
    return np.array(Image.open(ROOT/'assets'/name).convert('RGB'))

class ResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.reader=ResultReader()
    def test_settlement_with_touching_digits(self):
        r=self.reader.read(picture());self.assertEqual((r['score'],r['fruit_coins']),(4408,243))
    def test_unseen_recording(self):
        r=self.reader.read(picture('result_heldout.png'));self.assertEqual((r['score'],r['fruit_coins']),(1503,82))
    def test_physical_resolution_is_normalized(self):
        im=Image.fromarray(picture());r=self.reader.read(np.array(im.resize((654,1238))))
        self.assertEqual((r['score'],r['fruit_coins']),(4408,243))
    def test_zero_is_a_value_not_an_error(self):
        im=picture();zero=im[262:274,100:110].copy()
        im[261:275,71:144]=(255,252,221);im[262:274,94:104]=zero
        im[261:275,246:307]=(255,252,221);im[262:274,260:270]=zero
        r=self.reader.read(im);self.assertIsNotNone(r)
        self.assertEqual((r['score'],r['fruit_coins']),(0,0))
    def test_entry_and_blank_are_not_results(self):
        self.assertIsNone(self.reader.read(picture('entry_test.jpg')))
        self.assertIsNone(self.reader.read(np.zeros((619,327,3),np.uint8)))
    def test_unreadable_numbers_are_not_zero(self):
        im=picture();im[261:275,71:144]=0;self.assertIsNone(self.reader.read(im))
    def test_changed_digits_must_stabilize_again(self):
        s=StableResult();a={'score':1,'fruit_coins':2};b={'score':400,'fruit_coins':20}
        s.observe(a,0);s.observe(a,.15);s.observe(b,.31)
        self.assertFalse(s.ready(.32))
        s.observe(b,.5);s.observe(b,.7);self.assertTrue(s.ready(.7))
        self.assertFalse(s.ready(1.1))
    def test_engine_sends_result_and_no_preview(self):
        import engine
        from offline_test import FakeWindows
        clock=[0.];frames=[0];messages=[];fake=FakeWindows();cancel=threading.Event();rgb=picture()
        class Grab:
            def grab(self,rect):clock[0]+=.15;frames[0]+=1;return rgb
            def close(self):pass
        class Detector:
            def detect(self,_):
                return dict(active=frames[0]<5,targets=[],bombs=[],holes=[],hold=None,image=rgb,ui={})
        class App:
            closed=threading.Event();detector=Detector()
            def send(self,value):messages.append(value)
        with patch.object(engine.time,'monotonic',lambda:clock[0]):
            engine.run_engine(App(),7,'armed',cancel,fake,lambda h:(100,100,427,719),lambda:None,Grab)
        result=[v for k,v in messages if k=='complete'][-1]
        self.assertEqual((result['score'],result['fruit_coins']),(4408,243))
        self.assertFalse(any(k=='image' for k,v in messages));self.assertEqual(fake.events,[])
    def test_reward_outlier_is_not_used_as_the_duration(self):
        from engine import initial_reward_seconds
        self.assertEqual(initial_reward_seconds({12:29,11:7,17:5}),12)
        self.assertIsNone(initial_reward_seconds({12:1}))

if __name__=='__main__':unittest.main()
