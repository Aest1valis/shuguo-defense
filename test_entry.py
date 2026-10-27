"""Entry and stock checks use saved images and a fake desktop; no real clicks."""
from pathlib import Path
import threading,unittest
import numpy as np
from PIL import Image
from entry import EntryReader,EntryError,HammerInsufficient,checked_start

ROOT=Path(__file__).parent

def screenshot(normal_zero=False,luxury_ten=False):
    im=np.array(Image.open(ROOT/'assets'/'entry_test.jpg').convert('RGB'))
    zero=im[69:78,128:136].copy();one=im[69:78,194:198].copy()
    if normal_zero:
        im[68:79,188:209]=(54,68,57);im[69:78,199:207]=zero
    if luxury_ten:
        im[68:79,117:147]=(54,68,57)
        im[69:78,125:129]=one;im[69:78,132:140]=zero
    return im

class Desktop:
    def __init__(self,images):self.images=images;self.captures=0;self.clicks=[]
    def focus(self,cancel):pass
    def capture(self):
        i=min(self.captures,len(self.images)-1);self.captures+=1
        return (100,100,754,1338),self.images[i]
    def click(self,point,rect,cancel):self.clicks.append(point)

class EntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.reader=EntryReader()
    def test_real_recorded_counters(self):
        self.assertEqual(self.reader.read(screenshot()).counts,{'luxury':0,'normal':10})
    def test_both_zero_and_multiple_digits(self):
        self.assertEqual(self.reader.read(screenshot(True,True)).counts,{'luxury':10,'normal':0})
    def test_zero_deluxe_never_clicks(self):
        d=Desktop([screenshot()])
        with self.assertRaises(HammerInsufficient):checked_start('luxury',self.reader,d,threading.Event())
        self.assertEqual(d.clicks,[])
    def test_zero_normal_never_clicks(self):
        d=Desktop([screenshot(True,True)])
        with self.assertRaises(HammerInsufficient):checked_start('normal',self.reader,d,threading.Event())
        self.assertEqual(d.clicks,[])
    def test_each_button_uses_its_own_stock(self):
        d=Desktop([screenshot()]);checked_start('normal',self.reader,d,threading.Event())
        self.assertEqual(len(d.clicks),1);self.assertGreater(d.clicks[0][0],163)
        d=Desktop([screenshot(True,True)]);checked_start('luxury',self.reader,d,threading.Event())
        self.assertEqual(len(d.clicks),1);self.assertLess(d.clicks[0][0],163)
    def test_fresh_zero_blocks_even_after_positive_samples(self):
        d=Desktop([screenshot()]*3+[screenshot(True)])
        with self.assertRaises(HammerInsufficient):checked_start('normal',self.reader,d,threading.Event())
        self.assertEqual(d.clicks,[])
    def test_unreadable_count_is_not_permission_to_start(self):
        im=screenshot();im[68:80,117:147]=0;d=Desktop([im])
        with self.assertRaises(EntryError):checked_start('normal',self.reader,d,threading.Event())
        self.assertEqual(d.clicks,[])
    def test_wrong_page_is_not_clicked(self):
        d=Desktop([np.zeros((619,327,3),np.uint8)])
        with self.assertRaises(EntryError):checked_start('normal',self.reader,d,threading.Event())
        self.assertEqual(d.clicks,[])
    def test_cancel_does_not_click(self):
        d=Desktop([screenshot()]);cancel=threading.Event();cancel.set()
        self.assertIsNone(checked_start('normal',self.reader,d,cancel));self.assertEqual(d.clicks,[])

if __name__=='__main__':unittest.main()
