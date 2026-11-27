from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4,landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
import pypdfium2 as pdfium
from pypdf import PdfReader
import sys,json
from collections import Counter

combined=True
pending=True

import argparse,subprocess,tempfile,shutil,os
from datetime import datetime,date,timedelta
from zoneinfo import ZoneInfo
from scripts.daily539_report_data import remaining_groups,star_pairs,choose_target_date,figure_nine,whole_report_counts,omission_groups
from scripts.daily539_blank_report import calculate_blank_summaries
from scripts.california_daily import refresh as refresh_california
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--date',default=datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat())
parser.add_argument('--target-date')
args=parser.parse_args()
report_date=date.fromisoformat(args.date)
california=refresh_california(ROOT,report_date.isoformat())
data=json.loads(subprocess.check_output(['node',str(ROOT/'scripts/calculate_539_daily_report.cjs')],cwd=ROOT,text=True,encoding='utf-8'))
if data['cutoff']['draw_date']>report_date.isoformat():raise ValueError('Future dated source')
previous_file=ROOT/'docs/reports/daily539/latest.json'
previous_target=json.loads(previous_file.read_text(encoding='utf-8')).get('target_date') if previous_file.exists() else None
target_date=date.fromisoformat(args.target_date) if args.target_date else choose_target_date(report_date.isoformat(),data['cutoff']['draw_date'],previous_target)
groups=remaining_groups(data['draws'],target_date.isoformat(),data['cutoff']['draw_date'])
union=sorted({n for g in groups for n in g['numbers']})
figure=figure_nine(data['ranking'])
report_tables=calculate_blank_summaries(ROOT, include_ai=True)
blank_summaries=report_tables['blank_summaries']
ai_brief=report_tables['ai_brief']
omissions=omission_groups(data['draws'],data['cutoff']['draw_date'])
report_counts=whole_report_counts(data,[],figure,blank_summaries,ai_brief,california,omissions)
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
# Reserve a top strip for the 39-ball snapshot while keeping one landscape A4.
c.saveState()
c.translate(0, PH*(1-.81)-111)
c.scale(1,.81)
L=20; TOP=22; TOTAL=PW-40; left=32; right=0; cw=(TOTAL-left-right)/39; rh=15.25; hh=45
X=L+left; R=X+cw*39; BOT=TOP+hh+31*rh
ink='#000000';note='#000000';muted='#000000'
score_bands=[
 (4,'4分以上','#7c2bbd','#ffffff'),
 (3,'3分段','#c42938','#ffffff'),
 (2,'2分段','#a85a00','#ffffff'),
 (1,'1分段','#145ab4','#ffffff'),
 (0,'0分','#000000','#ffffff'),
]
scores_by_number={r['number']:r['score'] for r in data['ranking']}
def score_style(number):
 return next((foreground,background) for minimum,_,foreground,background in score_bands if scores_by_number[number]>=minimum)
def rect(x,y,w,h,fill,stroke=None):
 c.setFillColor(HexColor('#ffffff'));c.setStrokeColor(HexColor('#000000'));c.setLineWidth(.25);c.rect(x,PH-y-h,w,h,fill=1,stroke=bool(stroke))
def line(x1,y1,x2,y2,color='#a3a8a0',width=.3,dash=None):
 c.setStrokeColor(HexColor('#000000'));c.setLineWidth(min(width,.3));c.setDash([]);c.line(x1,PH-y1,x2,PH-y2);c.setDash([])

def middle_divider(x,y1,y2):
 c.setStrokeColor(HexColor('#000000'));c.setLineWidth(.3);c.setDash([2,2]);c.line(x,PH-y1,x,PH-y2);c.setDash([])
def txt(x,y,s,size=8,color=ink,align='center'):
 if color.lower() not in ('#000000', '#ffffff'):size*=.85
 c.setFillColor(HexColor(color));c.setFont('CJK',size)
 getattr(c,{'center':'drawCentredString','left':'drawString','right':'drawRightString'}[align])(x,PH-y-size*.35,str(s))
def cy(row):return TOP+hh+(row-.5)*rh
def cx(col):return X+(col-.5)*cw
rect(L,TOP,TOTAL,BOT-TOP,'#ffffff')
for i in range(40):
 if i!=20:line(X+i*cw,TOP+15,X+i*cw,BOT,'#9da49b',.35)
for x in [L,L+16,X,R]:line(x,TOP,x,BOT,'#525c52',.55)
for y in [TOP,TOP+15,TOP+30,TOP+hh,BOT]:line(L,y,L+TOTAL,y,'#525c52',.55)
for row in range(1,31):line(L,TOP+hh+row*rh,L+TOTAL,TOP+hh+row*rh,'#969e92',.3)
for row in [5,10,14,16,17,20,21,22,24,26,30]:line(L,TOP+hh+row*rh,R,TOP+hh+row*rh,'#4b574b',.75,[3,2])
for col in range(0,40,4):
 if col==20:middle_divider(X+col*cw,TOP,BOT)
 else:line(X+col*cw,TOP,X+col*cw,BOT,'#5b655a',.7,[3,2])
for group in range(10):
 a=group*4;b=min(a+4,39);txt(X+(a+b)*cw/2,TOP+7.5,group+1,9)
for col,label in [(4,'1*'),(5,'2*'),(7,'3*'),(11,'4*'),(17,'5*'),(19,'6*'),(24,'7*'),(26,'8*'),(28,'9*'),(35,'10*')]:txt(cx(col),TOP+23,label,7,muted)
for col in range(1,40):txt(cx(col),TOP+37.5,col,9)
for row in range(1,32):
 txt(L+24,cy(row),row if row<=27 else row-27,9)
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
  rect(X+(20+j)*cw+.4,TOP+hh+16*rh+(row-18)*10+.5,cw-.8,9,background)
  txt(X+20*cw+(j+.5)*cw,TOP+hh+16*rh+(row-18)*10+5,f'{n:02}',8.8,foreground)
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
  txt(px+panelw-6,py+9,'四組合併・不重複',6.3,muted,'right')
  meta='內建模擬 600 期｜種子 20261025｜W＝18 期' if source=='sim' else f"截至 {data['cutoff']['draw_date']}｜{data['cutoff']['draw_no']} 期｜W＝18"
  txt(px+7,py+25,meta,6.4,muted,'left')
  for i,group in enumerate(data[source]):
   yy=py+36+i*11
   txt(px+7,yy,names[group['strategy']][0],7.5,ink,'left')
   for j,n in enumerate(group['numbers']):
    txt(px+85+j*40,yy,f'{n:02}',9,score_style(n)[0])
   c.setStrokeColor(HexColor('#000000'));c.setLineWidth(.25);c.setDash([2,2])
   c.line(px,PH-(yy+5.5),px+panelw,PH-(yy+5.5));c.setDash([])

  numbers=sorted({n for g in data[source] for n in g['numbers']})
  txt(px+7,py+79,f'四組合併去重｜共 {len(numbers)} 碼｜由小到大',7.6,ink,'left')
  cols=10; cellw=panelw/cols; cellh=14
  number_top=py+85
  for q,n in enumerate(numbers):
   row,col=divmod(q,cols)
   bx=px+col*cellw; by=number_top+row*cellh
   rect(bx,by,cellw,cellh,'#ffffff','#000000')
   txt(bx+cellw/2,by+cellh/2,f'{n:02}',9.5,score_style(n)[0])
  repeated=sorted(n for n,count in Counter(n for g in data[source] for n in g['numbers']).items() if count>1)
  repeat_y=py+panelh-25
  rect(px,repeat_y,panelw,25,'#ffffff','#000000')
  txt(px+6,repeat_y+6,'重複號碼｜由小到大',6.5,ink,'left')
  for j,n in enumerate(repeated):
   txt(px+10+j*(panelw-20)/max(len(repeated),1),repeat_y+17,f'{n:02}',9,score_style(n)[0],'left')
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
  px=X+6; py=TOP+hh+16*rh+2; pw=19*cw-12; ph=5*rh-4
  ox=px; oy=py
  rect(ox,oy,px+pw-ox,ph,'#ffffff','#000000')
  txt(ox+5,oy+9,'遺漏統計｜3、1、8、9期',7.5,ink,'left')
  line(ox,oy+17,px+pw,oy+17)
  for i,group in enumerate(omissions):
   yy=oy+22+i*10
   txt(ox+5,yy,f"{group['gap']}期",8,ink,'left')
   label='、'.join(f'{n:02}' for n in group['numbers']) or '一'
   size=8
   while pdfmetrics.stringWidth(label,'CJK',size)>px+pw-ox-35 and size>5:size-=.25
   txt(ox+31,yy,label,size,ink,'left')
  txt(ox+5,oy+ph-12,'定義參考：樂透研究院',5.8,ink,'left')
  txt(ox+5,oy+ph-4,'截至 '+data['cutoff']['draw_date']+'｜當期開出＝漏0',5.5,ink,'left')
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
 # AI brief intersection sits in the remaining lower-left table cells.
 ax=X+6; ay=TOP+hh+25*rh+3; aw=19*cw-12; ah=6*rh-6
 rect(ax,ay,aw,ah,'#ffffff','#000000')
 split=ax+45
 line(split,ay,split,ay+ah)
 txt(ax+26,ay+9,'相鄰次數',8)
 txt(split+6,ay+9,'AI快報也有提及',9,ink,'left')
 line(ax,ay+17,ax+aw,ay+17)
 for i,group in enumerate(ai_brief['groups']):
  yy=ay+26+i*11.5
  txt(ax+26,yy,f"{group['count']}次",9)
  label='、'.join(f'{n:02}' for n in group['numbers']) or '—'
  color=next(fg for minimum,_,fg,_ in score_bands if group['count']>=minimum)
  txt(split+6,yy,label,8,color,'left')
  line(ax,yy+6,ax+aw,yy+6)
 brief_note='來源 '+ai_brief['source_draw_date']+'；共同提及非命中。'
 if ai_brief['source_draw_date']!=data['cutoff']['draw_date']:
  brief_note+='注意：資料日期不同。'
 txt(ax+5,ay+ah-4,brief_note,6,ink,'left')
 # Compact summaries are painted inside the original table, not below the image.
 bx=X+20*cw+3; by=TOP+hh+16*rh+43; bw=R-bx-6; bh=25*rh-16*rh-46
 rect(bx,by,bw,bh,'#fffefb','#a5b5a6')
 summary_entries=[]
 for summary in blank_summaries:
  label=f"近 {summary['long']} → {summary['short']} 期"
  grouped=summary['long']==18 and summary['short']==6
  if grouped:
   entries=[label]+[f"次數 {g['count']}／"+' '.join(f'{n:02}' for n in g['numbers']) for g in summary['groups']]
  else:
   entries=[label+'：'+' '.join(f'{n:02}' for g in summary['groups'] for n in g['numbers'])]
  summary_entries.append(entries)
 for summary_size in [9.5,9,8.5,8,7.5,7,6.5]:
  summary_lines=[]
  for entries in summary_entries:
   for text in entries:
    current=''
    for char in text:
     if pdfmetrics.stringWidth(current+char,'CJK',summary_size)>bw-12:
      summary_lines.append(current);current=''
     current+=char
    if current:summary_lines.append(current)
   summary_lines.append(None)
  required=sum(summary_size+0.5 if v is not None else 1 for v in summary_lines)
  if required<=bh-8:break
 else:raise ValueError('Blank summaries exceed table area')
 cursor=by+6
 for textline in summary_lines:
  if textline is None:cursor+=1
  else:
   txt(bx+6,cursor,textline,summary_size,ink,'left');cursor+=summary_size+0.5
 # Morning-only sources share the bottom band, after all evening calculations.
 mx=bx; my=ay; mw=bw; mh=ah
 rect(mx,my,mw,mh,'#ffffff','#000000')
 txt(mx+6,my+10,'白天 11:00 資料區｜加州天天樂',9,ink,'left')
 line(mx,my+19,mx+mw,my+19)
 ca=california['draw']
 txt(mx+6,my+32,report_date.isoformat()+(f"｜第{ca['draw_no']}期" if ca else '｜當日資料待更新'),9,ink,'left')
 txt(mx+6,my+50,'開出獎號：'+'　'.join(f'{n:02}' for n in ca['numbers']) if ca else '尚未取得當日有效獎號，等待更新。',11,ink,'left')
 txt(mx+6,my+mh-8,'來源：速彩｜以實際公布時間為準',7,ink,'left')
 txt(L,10,'今彩539｜上部：晚上 22:00 資料區　下部：白天 11:00 更新區',7,align='left')
 txt(L+TOTAL,10,f"{report_date.isoformat()}　資料截至 {data['cutoff']['draw_date']}",6.5,muted,'right')
else:
 txt(L,10,'今彩539｜依照片重繪・保留可辨識筆記',7,align='left')
txt(L,BOT+9,'相鄰排名／星號分色：',6.5,align='left')
for i,(_,label,foreground,background) in enumerate(score_bands):
 lx=L+83+i*70
 txt(lx,BOT+7,label,6.8,foreground,'left')
txt(L,BOT+20,'號碼每日依相鄰分數自動分色。日期選號：目標日前5、2、11、12日；無開獎日往前取最近一期。',6.5,align='left')
txt(L,BOT+30,'相鄰排名與八組號碼沿用網站算法；模擬600期、種子20261025、窗口18期。統計供參考，非開獎預測。',6.5,muted,align='left')
c.restoreState()
sx=20; sy=16; sw=PW-40; cellw=sw/39
rect(sx,sy,sw,55,'#ffffff','#000000')
txt(sx+5,sy+8,'最後一窗快照｜官網真實資料｜最後18期｜'+data['windowStart']['date']+'～'+data['cutoff']['draw_date'],8,ink,'left')
txt(sx+sw-5,sy+8,'依頻多→漏多排序；漏19＝整窗未出現',6.5,ink,'right')
line(sx,sy+16,sx+sw,sy+16)
for i,ball in enumerate(data['lastWindowSnapshot']):
 xx=sx+i*cellw
 if i:line(xx,sy+16,xx,sy+55)
 txt(xx+cellw/2,sy+24,f"{ball['number']:02}",8.5,score_style(ball['number'])[0])
 frequency_size=6*1.15 if ball['frequency']>=3 else 6
 frequency_label=str(ball['frequency'])
 frequency_width=pdfmetrics.stringWidth('頻','CJK',frequency_size)
 frequency_left=xx+(cellw-frequency_width-pdfmetrics.stringWidth(frequency_label,'CJK',6))/2
 txt(frequency_left,sy+36,'頻',frequency_size,ink,'left')
 txt(frequency_left+frequency_width,sy+36,frequency_label,6,ink,'left')
 txt(xx+cellw/2,sy+47,f"漏{ball['gap']}",6)
ry=77; ranking_height=36
rect(sx,ry,sw,ranking_height,'#ffffff','#000000')
txt(sx+5,ry+7,'全表球號出現次數｜由多至少・同次數按球號升序',7.5,ink,'left')
txt(sx+sw-5,ry+7,'不計底圖編號、日期、頻漏數值及本排序列',6,ink,'right')
line(sx,ry+13,sx+sw,ry+13)
for i,ball in enumerate(report_counts):
 xx=sx+i*cellw
 if i:line(xx,ry+13,xx,ry+ranking_height)
 txt(xx+cellw/2,ry+21,f"{ball['number']:02}",8.5,score_style(ball['number'])[0])
 txt(xx+cellw/2,ry+31,f"{ball['count']}次",6)
c.showPage();c.save()
assert len(PdfReader(p).pages)==1
doc=pdfium.PdfDocument(str(p));doc[0].render(scale=2).to_pil().save(p.with_suffix('.png'))
doc.close()
metadata={k:v for k,v in data.items() if k!='draws'}
metadata.update(report_date=report_date.isoformat(),target_date=target_date.isoformat(),provisional=provisional,remaining_groups=groups,remaining_numbers=union,stars=[{'number':n,'star':s} for n,s in pairs],generated_at=datetime.now(ZoneInfo('Asia/Taipei')).isoformat())
metadata['figure_nine']=figure
metadata['whole_report_number_counts']=report_counts
metadata['top_summary_numbers']={source:sorted({n for g in data[source] for n in g['numbers']}) for source in ['sim','real']}
metadata['top_repeated_numbers']={source:sorted(n for n,count in Counter(n for g in data[source] for n in g['numbers']).items() if count>1) for source in ['sim','real']}
metadata['blank_summaries']=blank_summaries
metadata['ai_brief_comparison']=ai_brief
metadata['omission_analysis']={'cutoff_date':data['cutoff']['draw_date'],'reference_url':'https://lotto.arclink.com.tw/Lotto39yltj.do','definition':'連續未開出期數；當期開出為0期，依總表官方開獎資料計算','groups':omissions}
metadata['california_daily']={key:value for key,value in california.items() if key!='draws'}
metadata['score_colors']=[{'minimum':minimum,'label':label,'foreground':foreground,'background':background} for minimum,label,foreground,background in score_bands]
(stage/'latest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
# Promote only after the complete one-page PDF and preview render successfully.
for name in ['latest.pdf','latest.png','latest.json']:shutil.copyfile(stage/name,out/name)
archive=out/'archive';archive.mkdir(exist_ok=True)
shutil.copyfile(p,archive/(report_date.isoformat()+'.pdf'))
(out/'archive.json').write_text(json.dumps(sorted([f.stem for f in archive.glob('*.pdf')],reverse=True))+'\n',encoding='utf-8')
print(f"Report {report_date} target {target_date}: cutoff {data['cutoff']['draw_date']}, {len(union)} remaining numbers, provisional={provisional}")
tmp.cleanup()
