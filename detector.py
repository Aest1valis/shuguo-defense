"""Offline-testable image recognition. This module never sends input."""
from pathlib import Path
import sys
import cv2
import numpy as np

BASE = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))

class Detector:
    WIDTH = 327

    def __init__(self):
        self.templates = {}
        # Nearby scales accommodate the WeChat title bar and aspect-ratio changes.
        self.target_names = ('plain', 'plain_upright', 'plain_round', 'plain_high',
                             'fruit', 'fruit_upright', 'fruit_round')
        for name in ('board', 'board_live', 'hold', 'ninja', 'bomb_head', 'clock_body','clock_body2','clock_live') + self.target_names:
            im = cv2.imdecode(np.fromfile(BASE / 'assets' / (name + '.png'), np.uint8), 0)
            if im is None:
                raise RuntimeError('缺少识别素材：' + name)
            self.templates[name] = [
                (s, cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA))
                for s in (.82, .88, .94, 1.0, 1.06, 1.12)
            ]

    def matches(self, gray, name, threshold, limit=8, scale_hint=None):
        hits = []
        for scale, template in self.templates[name]:
            if scale_hint is not None and abs(scale-scale_hint) > .065:
                continue
            h, w = template.shape
            if gray.shape[0] < h or gray.shape[1] < w:
                continue
            score = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            for _ in range(limit):
                _, value, _, (x, y) = cv2.minMaxLoc(score)
                if value < threshold:
                    break
                hits.append(dict(x=x+w/2, y=y+h/2, w=w, h=h,
                                 score=float(value), kind=name, scale=scale))
                x0, x1 = max(0, x-w//2), min(score.shape[1], x+w//2+1)
                y0, y1 = max(0, y-h//2), min(score.shape[0], y+h//2+1)
                score[y0:y1, x0:x1] = -1
        unique = []
        for hit in sorted(hits, key=lambda p: -p['score']):
            if not any(abs(hit['x']-q['x']) < 24 and abs(hit['y']-q['y']) < 24 for q in unique):
                unique.append(hit)
        return unique[:limit]

    def detect(self, rgb):
        h, w = rgb.shape[:2]
        normalized = cv2.resize(rgb, (self.WIDTH, round(h*self.WIDTH/w)))
        gray = cv2.cvtColor(normalized, cv2.COLOR_RGB2GRAY)
        # The in-round life/score/fruit labels are absent on the entry screen.
        search_end = min(gray.shape[0], 240)
        boards = self.matches(gray[:search_end], 'board', .74, 1)+self.matches(gray[:search_end],'board_live',.76,1)
        boards.sort(key=lambda b:-b['score'])
        result = dict(active=False, targets=[], bombs=[], unknown=[], hold=None, board_score=0., image=normalized)
        if not boards:
            return result
        board = boards[0]
        bx,by=round(board['x']),round(board['y'])
        if gray[max(0,by-5):by+5,max(0,bx-75):bx+75].mean()<115:
            return result
        result.update(active=True, board_score=board['score'])
        y0 = int(board['y'] + 72*board['scale'])
        y1 = min(gray.shape[0], int(board['y'] + 446*board['scale']))
        area = gray[y0:y1]
        holds = self.matches(area, 'hold', .79, 1, board['scale'])
        if holds:
            hold = holds[0]
            hold['y'] += y0 - 35*hold['scale']
            result['hold'] = hold
            return result
        if board['kind']=='board_live':
            # The nine fixed holes let us inspect the held object directly. This
            # avoids rescanning eight head templates across the entire board.
            centers=((164,282),(86,332),(242,332),(60,409),(164,409),
                     (269,409),(86,484),(242,484),(164,531))
            scale=board['scale'];dx=board['x']-163;dy=board['y']-145
            for hx,hy in centers:
                x=163+(hx-163)*scale+dx
                hole_y=145+(hy-145)*scale+dy
                head=dict(x=x,y=hole_y-43*scale,scale=scale,w=48*scale,h=46*scale,score=board['score'])
                x0,x1=max(0,round(x-24*scale)),min(normalized.shape[1],round(x+24*scale))
                y0p,y1p=max(0,round(hole_y-85*scale)),max(1,round(hole_y-15*scale))
                face=normalized[y0p:y1p,x0:x1]
                if face.size==0:continue
                hsv=cv2.cvtColor(face,cv2.COLOR_RGB2HSV)
                pale=int(np.count_nonzero((hsv[:,:,1]<90)&(hsv[:,:,2]>180)))
                if pale<55*scale*scale:continue
                masked=float(np.mean((hsv[:,:,1]<110)&(hsv[:,:,2]<110)))
                if masked>.07:
                    head['kind']='bomb';head['object_score']=masked
                    result['bombs'].append(head)
                    continue
                kind,confidence=self.classify_object(normalized,head)
                head['kind']=kind;head['object_score']=confidence
                if kind=='bomb':result['bombs'].append(head)
                elif kind in ('fruit','clock'):result['targets'].append(head)
            return result
        hits = []
        for name in ('ninja', 'bomb_head'):
            for hit in self.matches(area,name,.70,scale_hint=board['scale']):
                hit['y'] += y0+6*hit['scale']
                if not any(abs(hit['x']-q['x'])<30 and abs(hit['y']-q['y'])<35 for q in result['bombs']):
                    hit['kind']='bomb'
                    result['bombs'].append(hit)
        for name in self.target_names:
            for hit in self.matches(area, name, .76, scale_hint=board['scale']):
                hit['y'] += y0 + 6*hit['scale']
                hits.append(hit)
        for hit in sorted(hits, key=lambda p: -p['score']):
            if not any(abs(hit['x']-q['x']) < 30 and abs(hit['y']-q['y']) < 30
                       for q in result['targets']):
                if any(abs(hit['x']-q['x'])<32 and abs(hit['y']-q['y'])<45 for q in result['bombs']):
                    continue
                kind,confidence=self.classify_object(normalized,hit)
                hit['kind']=kind
                hit['object_score']=confidence
                if kind=='bomb':result['bombs'].append(hit)
                elif kind in ('fruit','clock'):result['targets'].append(hit)
                else:result['unknown'].append(hit)
        return result

    def classify_object(self,rgb,hit):
        x,y,s=hit['x'],hit['y'],hit['scale']
        x0,x1=max(0,round(x-24*s)),min(rgb.shape[1],round(x+24*s))
        y0,y1=max(0,round(y+9*s)),min(rgb.shape[0],round(y+51*s))
        body=rgb[y0:y1,x0:x1]
        if body.size==0:return 'unknown',0.
        hsv=cv2.cvtColor(body,cv2.COLOR_RGB2HSV)
        hue,sat,val=cv2.split(hsv)
        # Bombs have a large charcoal body; eyes and fruit details occupy far less area.
        charcoal=(sat<105)&(val<130)
        dark=float(np.mean(charcoal))
        if dark>.17:return 'bomb',dark
        colorful=(sat>110)&(val>110)&((hue>=25)|(hue<=8))
        _,_,stats,_=cv2.connectedComponentsWithStats(colorful.astype(np.uint8),8)
        blob=max(stats[1:,cv2.CC_STAT_AREA],default=0)
        if blob>65*s*s:return 'fruit',float(blob/body.shape[0]/body.shape[1])
        gray=cv2.cvtColor(body,cv2.COLOR_RGB2GRAY)
        clock=self.matches(gray,'clock_live',.57,1,s)
        if clock:return 'clock',clock[0]['score']
        white_fruit=self.matches(gray,'clock_body',.61,1,s)+self.matches(gray,'clock_body2',.60,1,s)
        if white_fruit:return 'fruit',white_fruit[0]['score']
        # The clock carrier has a pale dial/belly with dark clock hands. Wait
        # until this lower-body evidence is visible; a face alone is insufficient.
        pale=float(np.mean((sat<95)&(val>165)))
        if pale>.40 and .008<dark<.14:return 'clock',pale
        return 'unknown',0.
