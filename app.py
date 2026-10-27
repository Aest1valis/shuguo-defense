"""Two-button launcher with a fresh hammer-stock check before each game."""
import ctypes
from ctypes import wintypes
import json,queue,sys,threading,time,re
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import numpy as np
from detector_v2 import Detector
from capture import FrameGrabber
from entry import EntryReader,EntryError,HammerInsufficient,NAMES,checked_start

user32=ctypes.windll.user32
try:ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:user32.SetProcessDPIAware()
user32.GetForegroundWindow.restype=wintypes.HWND
user32.GetAncestor.argtypes=(wintypes.HWND,wintypes.UINT)
user32.GetAncestor.restype=wintypes.HWND
user32.IsWindow.argtypes=(wintypes.HWND,)
user32.IsIconic.argtypes=(wintypes.HWND,)
user32.GetClientRect.argtypes=(wintypes.HWND,ctypes.POINTER(wintypes.RECT))
user32.ClientToScreen.argtypes=(wintypes.HWND,ctypes.POINTER(wintypes.POINT))
user32.GetWindowTextLengthW.argtypes=(wintypes.HWND,)
user32.GetWindowTextW.argtypes=(wintypes.HWND,wintypes.LPWSTR,ctypes.c_int)
user32.WindowFromPoint.argtypes=(wintypes.POINT,)
user32.WindowFromPoint.restype=wintypes.HWND
user32.SetForegroundWindow.argtypes=(wintypes.HWND,)
user32.ShowWindow.argtypes=(wintypes.HWND,ctypes.c_int)

def find_game():
    windows=[]
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def collect(hwnd,_):
        if user32.IsWindowVisible(hwnd):
            size=user32.GetWindowTextLengthW(hwnd);buf=ctypes.create_unicode_buffer(size+1)
            user32.GetWindowTextW(hwnd,buf,size+1)
            if buf.value=='保卫向日葵':windows.append(hwnd)
        return True
    user32.EnumWindows(callback_type(collect),0)
    if len(windows)!=1:raise EntryError('请打开一个保卫向日葵游戏窗口。')
    return windows[0]

def bounds(hwnd):
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):raise EntryError('游戏窗口已关闭或最小化。')
    rect=wintypes.RECT()
    if not user32.GetClientRect(hwnd,ctypes.byref(rect)):raise EntryError('无法读取游戏窗口。')
    point=wintypes.POINT();user32.ClientToScreen(hwnd,ctypes.byref(point))
    if rect.right<200 or rect.bottom<300:raise EntryError('请完整显示游戏窗口。')
    return (point.x,point.y,point.x+rect.right,point.y+rect.bottom)

def release():user32.mouse_event(4,0,0,0,0)

class GameDesktop:
    def __init__(self,hwnd):self.hwnd=hwnd;self.grabber=None
    def focus(self,cancel):
        if user32.IsIconic(self.hwnd):user32.ShowWindow(self.hwnd,9)
        user32.SetForegroundWindow(self.hwnd)
        for _ in range(12):
            if cancel.is_set():return
            if user32.GetForegroundWindow()==self.hwnd:
                cancel.wait(.10);return
            cancel.wait(.04)
        raise EntryError('无法切换到游戏，请显示游戏窗口后重试。')
    def capture(self):
        if user32.GetForegroundWindow()!=self.hwnd:raise EntryError('游戏窗口失去前台，请重试。')
        rect=bounds(self.hwnd)
        if self.grabber is None:self.grabber=FrameGrabber()
        return rect,self.grabber.grab(rect)
    def click(self,point,rect,cancel):
        if cancel.is_set():return
        if bounds(self.hwnd)!=rect or user32.GetForegroundWindow()!=self.hwnd:raise EntryError('游戏窗口已变化，请重试。')
        scale=(rect[2]-rect[0])/327.
        x=round(rect[0]+point[0]*scale);y=round(rect[1]+point[1]*scale)
        if user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(x,y)),2)!=self.hwnd:
            raise EntryError('游戏按钮被遮挡，请移开遮挡后重试。')
        user32.SetCursorPos(x,y);user32.mouse_event(2,0,0,0,0)
        try:cancel.wait(.012)
        finally:release()
    def close(self):
        if self.grabber:self.grabber.close();self.grabber=None

class App:
    def __init__(self,hotkeys=True):
        self.root=tk.Tk();self.root.title('蔬果保卫战')
        self.root.geometry('640x660');self.root.minsize(640,640)
        self.root.configure(bg='#f3f6fb');self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.detector=Detector();self.entry_reader=EntryReader()
        self.events=queue.Queue()
        self.cancel=threading.Event();self.closed=threading.Event();self.thread=None
        self.mode='idle';self.stock={'luxury':None,'normal':None};self.selected_mode=None
        self.status=tk.StringVar(value='待命')
        self.count_vars={k:tk.StringVar(value='剩余 —') for k in NAMES}
        self.result_vars={k:tk.StringVar(value='—') for k in ('score','fruit_coins')}
        box=tk.Frame(self.root,bg='#f3f6fb');box.pack(fill='both',expand=True,padx=24,pady=22)
        top=tk.Frame(box,bg='#f3f6fb');top.pack(fill='x',pady=(0,20))
        tk.Label(top,text='蔬果保卫战',bg='#f3f6fb',fg='#17263b',font=('Microsoft YaHei UI',21,'bold')).pack(side='left')
        tk.Label(top,text='（作者：Aest1valis）',bg='#f3f6fb',fg='#65758a',font=('Microsoft YaHei UI',9)).pack(side='left',padx=(6,0))
        tk.Label(top,textvariable=self.status,bg='#f3f6fb',fg='#65758a',font=('Microsoft YaHei UI',10),wraplength=260,justify='right').pack(side='right')
        row=tk.Frame(box,bg='#f3f6fb');row.pack(fill='x');row.grid_columnconfigure(0,weight=1);row.grid_columnconfigure(1,weight=1)
        self.buttons={}
        for col,(mode,color,fg) in enumerate([('luxury','#edc367','#5b3d12'),('normal','#3979dd','#ffffff')]):
            b=tk.Button(row,text=NAMES[mode],command=lambda m=mode:self.start(m),
                        bg=color,fg=fg,activebackground=color,activeforeground=fg,
                        disabledforeground='#9099a5',relief='flat',bd=0,highlightthickness=0,
                        cursor='hand2',font=('Microsoft YaHei UI',17,'bold'),pady=22)
            b.grid(row=0,column=col,sticky='ew',padx=(0,7) if col==0 else (7,0));self.buttons[mode]=b
            tk.Label(row,textvariable=self.count_vars[mode],bg='#f3f6fb',fg='#7d899b',font=('Microsoft YaHei UI',10)).grid(row=1,column=col,pady=(8,18))
        card=tk.Frame(box,bg='#ffffff',highlightthickness=1,highlightbackground='#e3e8f0');card.pack(fill='both',expand=True)
        tk.Label(card,text='本局结算',bg='#ffffff',fg='#7d899b',font=('Microsoft YaHei UI',10)).pack(anchor='w',padx=18,pady=(12,4))
        result_row=tk.Frame(card,bg='#ffffff');result_row.pack(fill='both',expand=True,padx=12,pady=(4,16))
        result_row.grid_columnconfigure(0,weight=1);result_row.grid_columnconfigure(2,weight=1)
        result_row.grid_rowconfigure(0,weight=1)
        for col,key,label,color in [(0,'score','得分','#1c2b42'),(2,'fruit_coins','水果币','#b7801d')]:
            cell=tk.Frame(result_row,bg='#ffffff');cell.grid(row=0,column=col,sticky='nsew',padx=8)
            tk.Label(cell,text=label,bg='#ffffff',fg='#8b97a8',font=('Microsoft YaHei UI',10)).pack(pady=(5,3))
            tk.Label(cell,textvariable=self.result_vars[key],bg='#ffffff',fg=color,font=('Microsoft YaHei UI',28,'bold')).pack()
        tk.Frame(result_row,bg='#edf0f5',width=1).grid(row=0,column=1,sticky='ns',pady=8)
        footer=tk.Frame(box,bg='#f3f6fb');footer.pack(fill='x',pady=(14,0))
        self.stop_hint=tk.Label(footer,text='Esc 停止',bg='#f3f6fb',fg='#8b97a8',font=('Microsoft YaHei UI',9));self.stop_hint.pack(side='left')
        self.controls=queue.SimpleQueue();self.hotkey_thread_id=None;self.hotkey_thread=None
        if hotkeys:
            self.hotkey_thread=threading.Thread(target=self.hotkey_loop,daemon=True);self.hotkey_thread.start()
        self.root.bind('<Escape>',lambda event:self.stop());self.root.after(60,self.tick)

    def hotkey_loop(self):
        self.hotkey_thread_id=ctypes.windll.kernel32.GetCurrentThreadId()
        registered=bool(user32.RegisterHotKey(None,3002,0x4000,0x1B))
        if not registered:self.send(('hotkey_unavailable',None))
        try:
            message=wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message),None,0,0)>0:
                if self.closed.is_set():break
                if message.message==0x0312:
                    self.cancel.set();self.controls.put('stop')
        finally:
            if registered:user32.UnregisterHotKey(None,3002)

    def start(self,mode):
        if self.thread and self.thread.is_alive():return
        try:hwnd=find_game()
        except Exception as e:messagebox.showwarning('未能开始',str(e),parent=self.root);return
        self.cancel=threading.Event();self.selected_mode=mode;self.mode='checking';self.status.set('检测锤子…')
        for b in self.buttons.values():b.configure(state='disabled')
        self.thread=threading.Thread(target=self.worker,args=(hwnd,mode,self.cancel),daemon=True);self.thread.start()

    def worker(self,hwnd,mode,cancel):
        from engine import run_engine
        desktop=None
        try:
            if mode in NAMES:
                desktop=GameDesktop(hwnd)
                state=checked_start(mode,self.entry_reader,desktop,cancel,lambda c:self.send(('counts',c)))
                desktop.close();desktop=None
                if state is None or cancel.is_set():return
                self.send(('launching',mode))
                return run_engine(self,hwnd,'armed',cancel,user32,bounds,release,FrameGrabber,start_timeout=8)
            return run_engine(self,hwnd,mode,cancel,user32,bounds,release,FrameGrabber)
        except HammerInsufficient as e:self.send(('insufficient',str(e)))
        except EntryError as e:self.send(('entry_error',str(e)))
        except Exception as e:self.send(('entry_error','无法开始：'+str(e)))
        finally:
            if desktop:desktop.close()
            self.send(('finished',None))

    def stop(self):
        self.cancel.set();self.status.set('已停止')

    def send(self,value):
        if value[0]!='image':self.events.put(value)

    def show_result(self,result):
        for key in self.result_vars:
            value=result.get(key)
            self.result_vars[key].set('未识别' if value is None else f'{value:,}' if isinstance(value,int) else str(value))

    def set_counts(self,counts):
        self.stock.update(counts)
        for k in NAMES:self.count_vars[k].set(f'剩余 {self.stock[k]}' if self.stock[k] is not None else '剩余 —')

    def tick(self):
        if self.closed.is_set():return
        while not self.controls.empty():self.controls.get();self.stop()
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='counts':self.set_counts(value)
                elif kind=='launching':self.mode='running';self.status.set('正在开局…')
                elif kind=='started':
                    self.status.set('自动保卫中')
                    for value in self.result_vars.values():value.set('—')
                    k=self.selected_mode
                    if k in self.stock and self.stock[k] is not None:self.set_counts({k:max(0,self.stock[k]-1)})
                elif kind=='phase':self.status.set(f'第 {value} 阶段')
                elif kind=='reward':self.status.set('狂热奖励 · 持续长按')
                elif kind=='complete':
                    n=value['stage_count'];self.status.set(f'完成 · {n} 阶段全中' if value['game_verified_all_stages_full'] else '本局已结束')
                    self.show_result(value)
                elif kind in ('insufficient','entry_error'):
                    self.status.set('锤子不足' if kind=='insufficient' else '未开始')
                    self.root.lift();self.root.focus_force()
                    messagebox.showwarning('锤子不足' if kind=='insufficient' else '未能开始',value,parent=self.root)
                elif kind=='hotkey_unavailable':self.stop_hint.configure(text='左上角停止')
                elif kind=='finished':
                    self.mode='idle'
                    for b in self.buttons.values():b.configure(state='normal')
                elif kind=='status':
                    if value.startswith('已进入'):self.status.set('自动保卫中')
                    elif value.startswith('已停止：') and '阶段' not in value:self.status.set('已停止')
        except queue.Empty:pass
        self.root.after(60,self.tick)

    def close(self):
        self.closed.set();self.cancel.set()
        if self.thread:self.thread.join(timeout=1)
        if self.hotkey_thread_id:user32.PostThreadMessageW(self.hotkey_thread_id,0x0012,0,0)
        if self.hotkey_thread:self.hotkey_thread.join(timeout=.3)
        self.root.destroy()

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--self-test':
        app=App(hotkeys=False);app.root.withdraw();app.root.update_idletasks()
        assert app.root.title()=='蔬果保卫战'
        assert [app.buttons[k].cget('text') for k in NAMES]==['豪华保卫','普通保卫']
        assert not hasattr(app,'canvas')
        app.show_result({'score':0,'fruit_coins':0})
        assert app.result_vars['score'].get()=='0' and app.result_vars['fruit_coins'].get()=='0'
        app.show_result({'score':None,'fruit_coins':None})
        assert app.result_vars['score'].get()=='未识别'
        from results import ResultReader
        from PIL import Image
        fixture=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'assets'/'result_test.png'
        result=ResultReader().read(np.array(Image.open(fixture).convert('RGB')))
        assert (result['score'],result['fruit_coins'])==(4408,243)
        assert not app.detector.detect(np.zeros((634,335,3),dtype=np.uint8))['active']
        app.close();Path(sys.argv[2]).write_text(json.dumps({'name':'蔬果保卫战','startup':'ok','buttons':['豪华保卫','普通保卫'],'preview':False,'result_panel':'ok','result_reader':'ok','blank_frame':'no input'},ensure_ascii=False),encoding='utf-8')
    else:App().root.mainloop()
