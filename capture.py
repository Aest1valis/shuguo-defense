"""Reusable Windows screen buffer, for the user's explicitly started game bot."""
import ctypes
from ctypes import wintypes as W
import cv2
import numpy as np

U=ctypes.windll.user32
G=ctypes.windll.gdi32
U.GetDC.argtypes=(W.HWND,);U.GetDC.restype=W.HDC
U.ReleaseDC.argtypes=(W.HWND,W.HDC)
G.CreateCompatibleDC.argtypes=(W.HDC,);G.CreateCompatibleDC.restype=W.HDC
G.SelectObject.argtypes=(W.HDC,W.HANDLE);G.SelectObject.restype=W.HANDLE
G.DeleteDC.argtypes=(W.HDC,)
G.DeleteObject.argtypes=(W.HANDLE,)
G.BitBlt.argtypes=(W.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,W.HDC,ctypes.c_int,ctypes.c_int,W.DWORD)

class Header(ctypes.Structure):
    _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),('planes',W.WORD),
              ('bits',W.WORD),('compression',W.DWORD),('image_size',W.DWORD),
              ('xpels',W.LONG),('ypels',W.LONG),('used',W.DWORD),('important',W.DWORD)]
class Info(ctypes.Structure):
    _fields_=[('header',Header),('colors',W.DWORD*3)]
G.CreateDIBSection.argtypes=(W.HDC,ctypes.POINTER(Info),W.UINT,ctypes.POINTER(ctypes.c_void_p),W.HANDLE,W.DWORD)
G.CreateDIBSection.restype=W.HANDLE

class FrameGrabber:
    def __init__(self):
        self.screen=U.GetDC(None);self.memory=G.CreateCompatibleDC(self.screen)
        self.bitmap=None;self.old=None;self.size=None;self.array=None
        if not self.screen or not self.memory:raise RuntimeError('无法创建屏幕捕获缓冲区')
    def grab(self,rect):
        left,top,right,bottom=rect;w,h=right-left,bottom-top
        if self.size!=(w,h):
            if self.bitmap:
                G.SelectObject(self.memory,self.old);G.DeleteObject(self.bitmap)
            info=Info();info.header=Header(ctypes.sizeof(Header),w,-h,1,32,0,w*h*4,0,0,0,0)
            pointer=ctypes.c_void_p()
            self.bitmap=G.CreateDIBSection(self.screen,ctypes.byref(info),0,ctypes.byref(pointer),None,0)
            if not self.bitmap:raise RuntimeError('无法分配屏幕图像')
            self.old=G.SelectObject(self.memory,self.bitmap)
            self.array=np.ctypeslib.as_array((ctypes.c_uint8*(w*h*4)).from_address(pointer.value)).reshape((h,w,4))
            self.size=(w,h)
        if not G.BitBlt(self.memory,0,0,w,h,self.screen,left,top,0x00CC0020|0x40000000):
            raise RuntimeError('屏幕捕获失败')
        return cv2.cvtColor(self.array,cv2.COLOR_BGRA2RGB)
    def close(self):
        if self.bitmap:
            G.SelectObject(self.memory,self.old);G.DeleteObject(self.bitmap);self.bitmap=None
        if self.memory:G.DeleteDC(self.memory);self.memory=None
        if self.screen:U.ReleaseDC(None,self.screen);self.screen=None
