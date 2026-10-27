"""Input is fully mocked. Running this file cannot click the real game."""
import threading
from unittest.mock import patch
import numpy as np
from PIL import Image
import app

class FakeWindows:
    def __init__(self):self.events=[];self.foreground=7;self.covered=False
    def GetCursorPos(self,p):p._obj.x=100;p._obj.y=100
    def GetForegroundWindow(self):return self.foreground
    def GetAsyncKeyState(self,k):return 0
    def SetCursorPos(self,x,y):self.events.append(('move',x,y))
    def WindowFromPoint(self,p):return 7
    def GetAncestor(self,h,k):return 9 if self.covered else 7
    def mouse_event(self,flags,*args):self.events.append(('mouse',flags))

def frame(active=False,hold=False):
    hit=dict(x=150,y=300,score=.95,kind='fruit')
    return dict(active=active, targets=[hit] if active and not hold else [],
                hold=hit if hold else None, image=np.zeros((594,327,3),dtype=np.uint8))

def run_case(kind):
    bot=app.App.__new__(app.App)
    bot.closed=threading.Event();bot.cancel=threading.Event()
    bot.send=lambda value:None
    fake=FakeWindows()
    class FakeDetector:
        WIDTH=327
        n=0
        def detect(self,rgb):
            self.n+=1
            if self.n>16:bot.cancel.set()
            if kind=='entry':
                if self.n==4:bot.cancel.set()
                return frame()
            if kind=='focus' and self.n==3:fake.foreground=9
            if kind=='covered':fake.covered=True
            if kind in ('preview','covered') and self.n==5:bot.cancel.set()
            if kind=='hold_cancel' and self.n==5:bot.cancel.set()
            return frame(active=self.n<5,hold=kind=='hold_cancel')
    bot.detector=FakeDetector()
    class FakeGrabber:
        def grab(self,rect):return np.zeros((594,327,3),dtype=np.uint8)
        def close(self):pass
    with patch.object(app,'user32',fake),patch.object(app,'bounds',return_value=(100,100,427,694)),patch.object(app,'FrameGrabber',FakeGrabber):
        bot.worker(7,'preview' if kind=='preview' else 'armed',bot.cancel)
    down=sum(x==('mouse',2) for x in fake.events)
    up=sum(x==('mouse',4) for x in fake.events)
    if kind in ('entry','preview','covered'):assert down==up==0,(kind,fake.events)
    else:assert down>=1 and down==up,(kind,fake.events)
    assert all(100<=e[1]<427 and 100<=e[2]<694 for e in fake.events if e[0]=='move')
    print(kind, 'PASS',down,up)

if __name__=='__main__':
    for name in ('entry','preview','covered','normal','hold_cancel','focus'):
        run_case(name)
