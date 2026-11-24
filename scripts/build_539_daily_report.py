from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4,landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
import pypdfium2 as pdfium
from pypdf import PdfReader
import sys,json

combined=True
pending=True

import argparse,subprocess,tempfile,shutil,os
from datetime import datetime,date,timedelta
from zoneinfo import ZoneInfo
from scripts.daily539_report_data import remaining_groups,star_pairs,choose_target_date,figure_nine
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--date',default=datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat())
parser.add_argument('--target-date')
args=parser.parse_args()
report_date=date.fromisoformat(args.date)
data=json.loads(subprocess.check_output(['node',str(ROOT/'scripts/calculate_539_daily_report.cjs')],cwd=ROOT,text=True,encoding='utf-8'))
if data['cutoff']['draw_date']>report_date.isoformat():raise ValueError('Future dated source')
previous_file=ROOT/'docs/reports/daily539/latest.json'
previous_target=json.loads(previous_file.read_text(encoding='utf-8')).get('target_date') if previous_file.exists() else None
target_date=date.fromisoformat(args.target_date) if args.target_date else choose_target_date(report_date.isoformat(),data['cutoff']['draw_date'],previous_target)
groups=remaining_groups(data['draws'],target_date.isoformat(),data['cutoff']['draw_date'])
union=sorted({n for g in groups for n in g['numbers']})
figure=figure_nine(data['ranking'])
provisional=data['cutoff']['draw_date']<(target_date-timedelta(days=1)).isoformat()
fonts=[os.environ.get('NUMERIS_REPORT_FONT',''),'C:/Windows/Fonts/msjh.ttc','/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc']
font=next((f for f in fonts if f and Path(f).is_file()),None)
if not font:raise RuntimeError('Install fonts-wqy-zenhei or set NUMERIS_REPORT_FONT')
pdfmetrics.registerFont(TTFont('CJK',font,subfontIndex=0))
out=ROOT/'docs/reports/daily539';out.mkdir(parents=True,exist_ok=True)
tmp=tempfile.TemporaryDirectory();stage=Path(tmp.name)
p=stage/'latest.pdf'
c=canvas.Canvas(str(p),pagesize=landscape(A4));PW,PH=landscape(A4)
c.setTitle('今彩539 A4每日總表 '+report_date.isoformat())
L=20; TOP=22; TOTAL=PW-40; left=32; right=52; cw=(TOTAL-left-right)/39; rh=15.25; hh=45
X=L+left; R=X+cw*39; BOT=TOP+hh+31*rh
ink='#222a25';note='#153f67';muted='#778078'
score_bands=[
 (4,'4分以上','#7c2bbd','#f2e6fb'),
 (3,'3分段','#c42938','#fde8ec'),
 (2,'2分段','#a85a00','#fff0d9'),
 (1,'1分段','#145ab4','#e6f0ff'),
 (0,'0分','#69736f','#edf0ec'),
]
scores_by_number={r['number']:r['score'] for r in data['ranking']}
def score_style(number):
 return next((foreground,background) for minimum,_,foreground,background in score_bands if scores_by_number[number]>=minimum)
def rect(x,y,w,h,fill,stroke=None):
 c.setFillColor(HexColor(fill));c.setStrokeColor(HexColor(stroke or fill));c.rect(x,PH-y-h,w,h,fill=1,stroke=bool(stroke))
def line(x1,y1,x2,y2,color='#a3a8a0',width=.3,dash=None):
 c.setStrokeColor(HexColor(color));c.setLineWidth(width);c.setDash(dash or []);c.line(x1,PH-y1,x2,PH-y2);c.setDash([])
def txt(x,y,s,size=8,color=ink,align='center'):
 c.setFillColor(HexColor(color));c.setFont('CJK',size)
 getattr(c,{'center':'drawCentredString','left':'drawString','right':'drawRightString'}[align])(x,PH-y-size*.35,str(s))
def cy(row):return TOP+hh+(row-.5)*rh
def cx(col):return X+(col-.5)*cw
rect(L,TOP,TOTAL,BOT-TOP,'#ffffff')
for col in range(1,40):
 if col%2==0:rect(X+(col-1)*cw,TOP+15,cw,BOT-TOP-15,'#e2e4df')
for row in range(1,32):
 if row%2==0:
  for col in range(1,40):rect(X+(col-1)*cw,TOP+hh+(row-1)*rh,cw,rh,'#e9ebe7' if col%2 else '#d4d8d1')
for i in range(40):line(X+i*cw,TOP+15,X+i*cw,BOT,'#9da49b',.35)
for x in [L,L+16,X,R,R+20,R+36,L+TOTAL]:line(x,TOP,x,BOT,'#525c52',.55)
for y in [TOP,TOP+15,TOP+30,TOP+hh,BOT]:line(L,y,L+TOTAL,y,'#525c52',.55)
for row in range(1,31):line(L,TOP+hh+row*rh,L+TOTAL,TOP+hh+row*rh,'#969e92',.3)
for row in [5,10,14,16,17,20,21,22,24,26,30]:line(L,TOP+hh+row*rh,R,TOP+hh+row*rh,'#4b574b',.75,[3,2])
for col in range(0,40,4):line(X+col*cw,TOP,X+col*cw,BOT,'#5b655a',.7,[3,2])
for group in range(10):
 a=group*4;b=min(a+4,39);txt(X+(a+b)*cw/2,TOP+7.5,group+1,9)
for col,label in [(4,'1*'),(5,'2*'),(7,'3*'),(11,'4*'),(17,'5*'),(19,'6*'),(24,'7*'),(26,'8*'),(28,'9*'),(35,'10*')]:txt(cx(col),TOP+23,label,7,muted)
for col in range(1,40):txt(cx(col),TOP+37.5,col,9)
txt(R+10,TOP+23,str(report_date.year-1911)+'年',6.5)
for row in range(1,32):
 txt(L+24,cy(row),row if row<=27 else row-27,9)
 txt(R+28,cy(row),row,8)
 txt(R+44,cy(row),['一','二','三','四','五','六'][(row-1)%6],8)
 if row%2==0 and row<=24:txt(R+10,cy(row),f'{row//2}月',7)
labels={1:'20',2:'2',3:'3',4:'4',5:'5',6:'50',7:'2',8:'3',9:'4',10:'5',11:'100',12:'2',13:'3',14:'4',15:'1',16:'滿',17:'2',18:'1~3',19:'3',20:'3',21:'4',22:'1~2',23:'5',24:'2',25:'6',26:'2~3',27:'7',28:'1',29:'8',30:'有'}
for row,label in labels.items():txt(L+8,cy(row),label,7)
for row in range(1,32):
 if row in [16,22,26,28,31]:continue
 for col in range(1,40):
  if row in [6,11,18,23,24,25,27]:txt(cx(col),cy(row),col,6.1,'#7e877c')
  elif row<=14:txt(cx(col),cy(row),1 if row<=5 else 2 if row<=10 else 3,3.2,'#9ba395')
  elif row in [19,20,21] and 5<=col<=16:txt(cx(col),cy(row),col,6,'#939b8f')
for row in [15,22]:
 for col,label in [(4,'4*1'),(5,'5*2'),(7,'7*3'),(11,'11*4'),(17,'17*5'),(19,'19*6'),(26,'26*8'),(28,'28*9'),(35,'35*10')]:txt(cx(col),cy(row),label,4.6,'#8f968b')
for col,label in [(12,'*4'),(17,'*5'),(19,'*6'),(26,'*8')]:txt(cx(col),cy(17),label,8,'#91988c')
ranking=[r['number'] for r in data['ranking']]
for col,n in enumerate(ranking,1):
 foreground,background=score_style(n)
 rect(X+(col-1)*cw+.4,TOP+hh+15*rh+.5,cw-.8,rh-1,background)
 txt(cx(col),cy(16),f'{n:02}',8.8,foreground)
matrix=[ranking[row::4] for row in range(4)]
for row,nums in enumerate(matrix,18):
 for j,n in enumerate(nums):
  foreground,background=score_style(n)
  rect(X+(20+j)*cw+.4,TOP+hh+(row-1)*rh+.5,cw-.8,rh-1,background)
  txt(X+20*cw+(j+.5)*cw,cy(row),f'{n:02}',8.8,foreground)
def circle(col,row,double=False,question=False):
 if question:
  c.setFillColor(HexColor('#ffffff'));c.circle(cx(col),PH-cy(row),6.5,fill=1,stroke=0)
 c.setStrokeColor(HexColor('#8c9489'));c.setLineWidth(.6);c.circle(cx(col),PH-cy(row),6.5,fill=0,stroke=1)
 if double:c.circle(cx(col),PH-cy(row),4.2,fill=0,stroke=1)
 if question:txt(cx(col),cy(row),'?',5.7,'#a65322')
for row in [22,26]:
 for col in [4,5,8,12,13]:circle(col,row)
for row in [25,28]:
 for col in [7,10,17,26,28]:circle(col,row,True,False)
txt(X+4*cw,cy(31),'（2　4　5　7）',8)
footer=[(10,'滿'),(12,'2'),(13,'1~3'),(15,'3'),(17,'4'),(18,'1~2'),(20,'5'),(21,'2'),(23,'6'),(24,'2~3'),(26,'7'),(27,'1'),(29,'8'),(30,'有')]
for col,s in footer:txt(cx(col),cy(31),s,7)
txt(R-12,cy(30),'m　0　0　3~4',6,align='right')
if combined:
 assert ranking==[r['number'] for r in data['ranking']]
 panelgap=8; panelw=(R-X-12-panelgap)/2; paneltop=TOP+hh+4; panelh=rh*10-8
 names={'hot':('熱號','頻率最高 5 碼'),'cold':('冷號','頻率最低 5 碼'),'overdue':('遺漏回補','遺漏最大 5 碼'),'hybrid':('混合','熱號 3 碼＋遺漏 2 碼')}
 for k,source in enumerate(['sim','real']):
  px=X+6+k*(panelw+panelgap); py=paneltop
  color='#80672c' if source=='sim' else '#1c5845'
  rect(px,py,panelw,panelh,'#fffefb','#a5b5a6')
  rect(px,py,panelw,18,'#f4f0e4' if source=='sim' else '#edf4ee','#a5b5a6')
  txt(px+7,py+9,'隨機模擬資料' if source=='sim' else '官網真實資料',9,color,'left')
  txt(px+panelw-6,py+9,'四組各 5 碼',6.3,muted,'right')
  meta='內建模擬 600 期｜種子 20261025｜W＝18 期' if source=='sim' else f"截至 {data['cutoff']['draw_date']}｜{data['cutoff']['draw_no']} 期｜W＝18"
  txt(px+7,py+25,meta,6.4,muted,'left')
  rowh=(panelh-34)/4
  for j,g in enumerate(data[source]):
   ry=py+34+j*rowh;line(px,ry,px+panelw,ry,'#c0cabe',.35)
   a,b=names[g['strategy']];txt(px+7,ry+7,a,7.6,ink,'left');txt(px+7,ry+16,b,5.8,muted,'left')
   for q,n in enumerate(g['numbers']):
    bx=px+panelw-118+q*24
    ball_color=score_style(n)[0]
    c.setFillColor(HexColor('#fffefb'));c.setStrokeColor(HexColor(ball_color));c.setLineWidth(.6)
    c.setDash([2,1.5]);c.circle(bx,PH-(ry+rowh/2),8,fill=1,stroke=1);c.setDash([])
    txt(bx,ry+rowh/2,f'{n:02}',10,ball_color)
 pairs=star_pairs(data['ranking'])
 sy=TOP+hh+rh*10+5; sx=X+6; sw=R-X-12; sh=rh*4-11
 rect(sx,sy,sw,sh,'#fffefb','#a5b5a6');rect(sx,sy,sw,15,'#edf1eb','#a5b5a6')
 txt(sx+7,sy+7.5,'星號對應球號｜依球號由小到大',8,ink,'left')
 for j,(n,star) in enumerate(pairs):
  a=sx+j*sw/10
  if j:line(a,sy+15,a,sy+sh,'#b4bfb0',.4)
  txt(a+sw/20,sy+25,f'{n:02}',11,score_style(n)[0])
  txt(a+sw/20,sy+39,f'{star}*',7.8,muted)
 if pending:
  selected=[(g['source_date'][5:].replace('-','/'),g['numbers']) for g in groups]
  px=X+6; py=TOP+hh+16*rh+2; pw=19*cw-12; ph=5*rh-4
  rect(px,py,pw,ph,'#fffefb','#a5b5a6');rect(px,py,pw,12,'#edf3ef','#a5b5a6')
  txt(px+6,py+6,target_date.strftime('%m/%d')+' 未再開出號碼｜'+('暫算' if provisional else '已扣至前一日'),8,note,'left')
  for j,(dt,ns) in enumerate(selected):
   yy=py+17+j*9.5
   txt(px+7,yy,dt,7.2,ink,'left')
   txt(px+49,yy,('、'.join(f'{n:02}' for n in ns) or ('已全數再開出' if groups[j]['available'] else '當日無開獎資料')),8.2,note,'left')
  line(px,py+52,px+pw,py+52,'#c0cabe',.35)
  txt(px+6,py+58,f'共{len(union)}碼：'+' '.join(f'{n:02}' for n in union),6.9,note,'left')
  txt(px+6,py+67,f"截至{data['cutoff']['draw_date'][5:]}；"+('尚待前一日開獎資料，非最終名單。' if provisional else '已扣除來源日之後至截止日重複獎號。'),6.6,'#a65322','left')
 if pending:
  fx=X+6; fy=TOP+hh+21*rh+3; fw=19*cw-12; fh=55
  rect(fx,fy,fw,fh,'#fffefb','#a5b5a6')
  rect(fx,fy,fw,13,'#edf3ef','#a5b5a6')
  shape='、'.join(str(n) for n in figure['shape'])
  txt(fx+6,fy+6.5,'每日圖形9碼｜'+report_date.strftime('%m/%d')+'・'+shape,7.6,note,'left')
  txt(fx+6,fy+24,'　'.join(f'{n:02}' for n in figure['sorted_numbers']),11.3,note,'left')
  order='｜'.join('、'.join(f'{n:02}' for n in col['numbers']) for col in figure['columns'])
  txt(fx+6,fy+40,'左起順序：'+order,6.9,note,'left')
  txt(fx+6,fy+50,'依最新排名及整數分組重算；統計參考。',6,muted,'left')
 txt(L,10,'今彩539｜A4 格表・八組號碼、星號對照'+('及日期選號' if pending else ''),7,align='left')
 txt(L+TOTAL,10,f"{report_date.isoformat()}　資料截至 {data['cutoff']['draw_date']}",6.5,muted,'right')
else:
 txt(L,10,'今彩539｜依照片重繪・保留可辨識筆記',7,align='left')
txt(L,BOT+9,'相鄰排名／星號分色：',6.5,align='left')
for i,(_,label,foreground,background) in enumerate(score_bands):
 lx=L+83+i*70
 rect(lx,BOT+3,8,8,background,foreground)
 txt(lx+12,BOT+7,label,6.8,foreground,'left')
txt(L,BOT+20,'號碼每日依相鄰分數自動分色；灰圈為原底圖固定記號。日期選號：目標日前5、3、11、12日；未開獎日不替補。',6.5,align='left')
txt(L,BOT+30,'相鄰排名與八組號碼沿用網站算法；模擬600期、種子20261025、窗口18期。統計供參考，非開獎預測。',6.5,muted,align='left')
c.showPage();c.save()
assert len(PdfReader(p).pages)==1
doc=pdfium.PdfDocument(str(p));doc[0].render(scale=2).to_pil().save(p.with_suffix('.png'))
doc.close()
metadata={k:v for k,v in data.items() if k!='draws'}
metadata.update(report_date=report_date.isoformat(),target_date=target_date.isoformat(),provisional=provisional,remaining_groups=groups,remaining_numbers=union,stars=[{'number':n,'star':s} for n,s in pairs],generated_at=datetime.now(ZoneInfo('Asia/Taipei')).isoformat())
metadata['figure_nine']=figure
metadata['score_colors']=[{'minimum':minimum,'label':label,'foreground':foreground,'background':background} for minimum,label,foreground,background in score_bands]
(stage/'latest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
# Promote only after the complete one-page PDF and preview render successfully.
for name in ['latest.pdf','latest.png','latest.json']:shutil.copyfile(stage/name,out/name)
archive=out/'archive';archive.mkdir(exist_ok=True)
shutil.copyfile(p,archive/(report_date.isoformat()+'.pdf'))
(out/'archive.json').write_text(json.dumps(sorted([f.stem for f in archive.glob('*.pdf')],reverse=True))+'\n',encoding='utf-8')
print(f"Report {report_date} target {target_date}: cutoff {data['cutoff']['draw_date']}, {len(union)} remaining numbers, provisional={provisional}")
tmp.cleanup()
