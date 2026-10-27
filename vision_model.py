"""Small visual state classifier. Training libraries are not needed at runtime."""
from pathlib import Path
import sys
import cv2
import numpy as np

CLASSES=('empty','good','bomb','hit','transition')

def features(rgb):
    im=cv2.resize(rgb,(48,64),interpolation=cv2.INTER_AREA)
    color=cv2.resize(im,(24,32)).astype(np.float32).reshape(-1)/255.
    hsv=cv2.resize(cv2.cvtColor(im,cv2.COLOR_RGB2HSV),(16,24)).astype(np.float32).reshape(-1)/255.
    gray=cv2.cvtColor(im,cv2.COLOR_RGB2GRAY)
    gx=cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3)
    gy=cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3)
    edge=cv2.resize(cv2.magnitude(gx,gy),(16,24)).reshape(-1)/1024.
    return np.concatenate((color,hsv,edge))

class VisualStateModel:
    def __init__(self,path=None):
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
        z=np.load(path or root/'assets'/'state_model.npz')
        for name in ('roots','feature','threshold','left','right','prob'):
            setattr(self,name,z[name])
        self.depth=int(z['depth'])

    def predict(self,patches):
        x=np.stack([features(p) for p in patches]).astype(np.float32)
        nodes=np.tile(self.roots,(len(x),1))
        sample=np.arange(len(x))[:,None]
        for _ in range(self.depth+1):
            v=x[sample,self.feature[nodes]]
            nodes=np.where(v<=self.threshold[nodes],self.left[nodes],self.right[nodes])
        return self.prob[nodes].mean(axis=1)
