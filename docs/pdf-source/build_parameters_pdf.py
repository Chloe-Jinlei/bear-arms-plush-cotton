from pathlib import Path
from xml.sax.saxutils import escape
from itertools import groupby
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,PageBreak,KeepTogether
from pypdf import PdfReader

BASE=Path('/run/user/1000/bear-material-task')
OUT=BASE/'output/pdf/熊与棉布_物理参数设置_plush_cotton.pdf'
for name,path in [('CJK','/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf'),('Latin','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),('LatinBold','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')]:
 pdfmetrics.registerFont(TTFont(name,path))
NAVY=colors.HexColor('#183A50'); TEAL=colors.HexColor('#167D8D'); INK=colors.HexColor('#23333F'); MUTED=colors.HexColor('#5D6E7A'); PALE=colors.HexColor('#EFF5F7'); LINE=colors.HexColor('#D6E2E7')
W,H=A4; margin=42; width=W-2*margin
styles={
 'title':ParagraphStyle('title',fontName='Latin',fontSize=22,leading=30,textColor=NAVY,spaceAfter=8,wordWrap='CJK'),
 'subtitle':ParagraphStyle('subtitle',fontName='Latin',fontSize=10,leading=16,textColor=MUTED,spaceAfter=12,wordWrap='CJK'),
 'body':ParagraphStyle('body',fontName='Latin',fontSize=9.2,leading=14,textColor=INK,spaceAfter=7,wordWrap='CJK'),
 'small':ParagraphStyle('small',fontName='Latin',fontSize=8.4,leading=12.5,textColor=MUTED,spaceAfter=6,wordWrap='CJK'),
 'section':ParagraphStyle('section',fontName='Latin',fontSize=12.5,leading=19,textColor=TEAL,spaceBefore=7,spaceAfter=7,wordWrap='CJK'),
 'cell':ParagraphStyle('cell',fontName='Latin',fontSize=8.6,leading=12.8,textColor=INK,wordWrap='CJK',splitLongWords=True),
 'head':ParagraphStyle('head',fontName='Latin',fontSize=9,leading=13,textColor=colors.white,wordWrap='CJK'),
}
cjkmap=pdfmetrics.getFont('CJK').face.charToGlyph
latinmap=pdfmetrics.getFont('Latin').face.charToGlyph
all_text=[]
def font_for(c):
 return 'CJK' if ord(c)>=0x2E80 and ord(c) in cjkmap else 'Latin'
def rich(s):
 all_text.append(s)
 parts=[]
 for name,cs in groupby(s,font_for):
  t=''.join(cs)
  missing=[x for x in t if x not in '\n\t' and ord(x) not in pdfmetrics.getFont(name).face.charToGlyph]
  if missing: raise ValueError(('Missing glyph',name,missing))
  parts.append('<font name="'+name+'">'+escape(t).replace('\n','<br/>')+'</font>')
 return ''.join(parts)
def p(s,style='body'):return Paragraph(rich(s),styles[style])
story=[]
def para(s,style='body'):story.append(p(s,style))
def title(n,s,sub):
 if n>1:story.append(PageBreak())
 para(f'{n:02d}  {s}','title');para(sub,'subtitle')
def section(s):para(s,'section')
def table(headers,rows,ratios=None):
 if ratios is None:ratios=[.39,.25,.36] if len(headers)==3 else [.46,.54]
 data=[[p(str(x),'head') for x in headers]]+[[p(str(x),'cell') for x in r] for r in rows]
 t=Table(data,colWidths=[width*x for x in ratios],hAlign='LEFT',repeatRows=1)
 t.setStyle(TableStyle([
 ('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
 ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
 ('TOPPADDING',(0,0),(-1,0),7),('BOTTOMPADDING',(0,0),(-1,0),7),
 ('TOPPADDING',(0,1),(-1,-1),5),('BOTTOMPADDING',(0,1),(-1,-1),5),
 ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),
 ('LINEBELOW',(0,0),(-1,0),.6,TEAL),('LINEBELOW',(0,1),(-1,-1),.25,LINE),
 ]))
 story.extend([t,Spacer(1,9)])

title(1,'熊与棉布物理参数设置','材料版本：plush_cotton  |  仿真版本：2026-10-27  |  导出日期：2026-10-29')
para('适用范围：已交付完整录像所用的场景参数。包含材料设置、代码中的实际覆盖值，以及影响材料表现的接触与求解设置。动作代码和 assets 保持原样。','small')
section('熊 / 可压缩填充体与表面边网络')
para('熊的表面与内部属于同一个四面体网格，以不同边柔度区分；没有新增独立布壳或毛发物理层。柔度 compliance 越大，约束越软。','small')
table(['参数 / 配置键','实际数值','说明'],[
('总质量 mass','0.49 kg','保持原值'),
('初始体积 / 平均密度','0.01636847 m³\n29.9356 kg/m³','密度由质量÷网格体积推算'),
('粒子 / 四面体数量','1832 / 7623','原网格；节点等质量分配'),
('单粒子质量','0.000267467 kg','不是逐单元均匀密度标定'),
('压缩体积模量\nbulk_modulus_compression_pa','3000 Pa = 3 kPa','压缩响应'),
('膨胀体积模量\nbulk_modulus_expansion_pa','15000 Pa = 15 kPa','膨胀响应'),
('内部边柔度\ninternal_stretch_compliance','0.01 m/N','内部更容易形变'),
('表面边柔度\nsurface_stretch_compliance','0.001 m/N','表面边约束更强'),
('拉伸松弛 stretch_relaxation','0.1','数值求解设置'),
('轴向阻尼 internal_damping_per_s','40 s⁻¹','逐边按 40/27 ≈ 1.4815 s⁻¹ 使用'),
('形变阻尼 shape_damping_per_s','20 s⁻¹','只耗散扣除刚体运动后的剩余速度'),
('静 / 动摩擦','0.7 / 0.5','friction / kinetic_friction'),
('体积基础松弛 bulk_relaxation','1.0','再除以最大四面体邻接数'),
('体积比目标 minimum_volume_ratio','0.10','J = 当前有向体积 / 初始体积'),
('单约束位置修正上限','0.001 m = 1 mm','maximum_volume_correction_m'),
('固定底部 fixed_band_height','0.018 m；92 个粒子','运行值优先于资产 metadata'),
('初始底部离桌 base_clearance','0.003 m = 3 mm','初始条件'),
],[.43,.25,.32])
para('体积柔度按四面体计算：α = 1/(K × V₀)，单位 J⁻¹。未直接设置统一杨氏模量或泊松比，也未单独建立塑性压实、纤维滑移模型。J = 0.10 是投影目标，不能保证所有时刻无翻转。','small')

title(2,'棉布参数','二维织物网格  |  原尺寸与两个真实袖孔保持不变')
table(['参数 / 配置键','实际数值','说明'],[
('外形尺寸','0.86 × 0.20 m','保持原值'),
('扣孔后的实际面积','0.16327536 m²','按实际网格计算质量'),
('面密度 areal_density','0.18 kg/m² = 180 g/m²','不是体密度'),
('总质量','0.0293896 kg ≈ 29.39 g','面密度 × 实际面积'),
('粒子数量 / 单粒子质量','1153 / 0.00002548965 kg','节点等质量分配'),
('拉伸柔度 stretch_compliance','1 × 10⁻⁷ m/N','原生拉伸约束仍有效'),
('拉伸求解松弛','0.3','Genesis 默认值'),
('弯曲刚度 bending_rigidity_nm','5 × 10⁻⁵ N·m','二面角弯曲模型'),
('弯曲松弛 / 迭代次数','0.5 / 4 次','每次弯曲求解'),
('经向 warp_max_extension','0.02 = 2%','原始布料 X 方向'),
('纬向 weft_max_extension','0.02 = 2%','原始布料 Y 方向'),
('斜向 bias_max_extension','0.10 = 10%','其他网格边'),
('伸长迭代 strain_limit_iterations','24 轮','每次原生拉伸求解之后'),
('内部阻尼 internal_damping_per_s','4 s⁻¹','逐边按 4/8 = 0.5 s⁻¹ 使用'),
('静 / 动摩擦','0.6 / 0.45','friction / kinetic_friction'),
('空气密度 air_density_kg_m3','1.225 kg/m³','用于空气阻力'),
('阻力系数 air_drag_coefficient','1.0','无量纲'),
('初始离桌 initial_clearance','0.006 m = 6 mm','初始条件'),
],[.43,.27,.30])
section('弯曲与空气阻力的换算')
para('弯曲约束：kθ = 3Bℓ²/(A₁ + A₂)。B 为弯曲刚度，ℓ 为相邻三角形的公共边长，A₁、A₂ 为静止面积。弯曲乘子每个物理子步清零一次。')
para('空气阻力：Fᵢ = −0.5ρCdAᵢ|vᵢ|vᵢ。按每个节点代表的面积计算，逐点系数范围为 1.59043 × 10⁻⁵ 至 1.27234 × 10⁻⁴ kg/m。')
para('未单独设置真实布厚、棉纤维体密度、杨氏模量或泊松比。2 mm 接触间距、4 mm 粒子直径都不是实际棉布厚度。经 / 纬 / 斜向的 2% / 2% / 10% 是拉伸投影目标；有限迭代和后续接触允许残差超限。','small')

title(3,'魔术贴参数','接触触发的局部无滑移粘接  |  沿用原逻辑')
para('该模型以接触几何与持续时间决定激活、断开。魔术贴不额外增加质量或厚度，没有以 N 表示的拉脱力或剥离强度参数。')
table(['参数 / 配置键','实际数值'],[
('每条粘接区域尺寸','40 × 200 mm'),
('边缘内缩 strip_inset_m','0 mm'),
('激活距离 activation_distance_m','5 mm'),
('法线角容差 normal_angle_tolerance_deg','35°'),
('相向接触容差 facing_tolerance_m','1 mm'),
('连续接触时间 dwell_time_s','0.08 s = 80 ms'),
('断开分离误差 break_error_m','15 mm'),
('断开持续时间 break_dwell_time_s','误差超过阈值并持续 0.08 s'),
('每子步迭代 iterations_per_substep','12'),
('求解松弛 relaxation','0.9'),
('单次修正上限 max_correction_per_pass_m','2 mm'),
('方向符号 surface_signs','left = +1；right = +1'),
],[.59,.41])
section('粘接附近的数值稳定设置')
table(['项目','设置'],[
('局部原长约束区域','布两端各 100 mm'),
('局部原长投影次数','每轮粘接后 4 次'),
('局部原长投影松弛','0.2'),
('分母正则项','0.1 kg⁻¹'),
('末尾处理','12 轮结束后，再补 1 次粘接投影'),
],[.46,.54])
para('上述局部投影用于减小求解中的应力集中，是数值设置，不是魔术贴材料试验参数。15 mm 是几何误差阈值，不是力阈值；一次局部粘接也不代表整条魔术贴已完全贴合。','small')


title(4,'桌面、地面与机械臂','刚体与夹持设置保持原样')
table(['参数','桌面 / 地面 / 支架','机械臂 / 夹爪'],[
('物理类型','固定刚体','Panda 关节刚体模型'),
('刚体间摩擦 friction','0.7','沿用 MJCF 模型'),
('软体耦合摩擦 coup_friction','0.7','0.7'),
('参与耦合 needs_coup','开启','开启'),
('重力补偿 gravity_compensation','0；物体固定','1.0'),
('质量与惯量','未单独标定；固定不动','沿用原 Panda 模型'),
('SDF 单元尺寸','5 mm','5 mm'),
('SDF 分辨率上下限','32 至 128','32 至 128'),
],[.40,.30,.30])
section('几何与夹爪质量')
table(['项目','设置'],[
('桌面尺寸 / 桌面高度','1.55 × 1.05 × 0.07 m / 0.74 m'),
('每个手指的模型质量','0.015 kg'),
('每个手掌的模型质量','0.73 kg'),
('抓取后的节点约束','接触触发的理想局部无滑移附着'),
('夹爪垫弹性','未另外设置橡胶垫的弹性模量'),
],[.46,.54])
para('刚体接口保留默认 coup_restitution = 0、coup_softness = 0.002。当前自定义刚体与 PBD 接触采用直接位置投影，这两个接口值不直接控制该接触的反弹或柔度。','small')
section('摩擦系数的实际配对规则')
table(['接触组合','静 / 动摩擦','组合规则'],[
('熊与桌面或夹爪','0.7 / 0.5','取粒子系数与刚体耦合系数的较小值'),
('棉布与桌面或夹爪','0.6 / 0.45','取双方较小值'),
('原生熊与布粒子接触','0.7 / 0.5','取双方较大值'),
('额外布与熊表面接触','0.2 / 0.2','独立附加层，见下一页'),
],[.40,.24,.36])
para('夹持节点跟随真实机器人连杆变换。该理想附着不是基于橡胶摩擦的力闭合模型；夹持负载没有通过该附着约束回传机械臂。','small')


title(5,'附加接触与防翻转设置','接触分层存在  |  各层参数不能合并成一个摩擦系数或厚度')
section('布与熊的附加表面接触')
table(['参数','设置'],[
('摩擦系数','0.2'),
('表面间隙 / 搜索距离','2 mm / 20 mm'),
('每子步迭代次数','8'),
('单点每轮修正上限','min(1 mm, 该点最短相邻边的 10%)'),
('熊响应比例 body_response_scale','0；此附加层只修正布'),
('作用范围','将当前形变后的熊表面作为障碍；原生粒子接触及机器人与熊的动力学仍生效'),
],[.46,.54])
section('布两端之间的附加面接触')
table(['参数','设置'],[
('区域宽度','100 mm'),
('数值接触间距 / 厚度','2 mm'),
('接触搜索距离','12 mm'),
('接触历史释放距离','20 mm'),
('每子步迭代 / 松弛','3 / 0.8'),
('单次位置修正上限','0.3 mm'),
('摩擦与粘接','本附加层无摩擦、无粘接'),
('位置响应','双向质量加权修正；不处理同一区域内部的自接触'),
],[.46,.54])
section('附加正体积投影')
table(['参数','设置'],[
('有向体积比目标 J_min','0.1'),
('松弛系数','0.7'),
('每次调用的投影次数','3'),
('每轮位置修正上限','0.25 mm'),
],[.46,.54])
para('附加正体积投影与第 1 页的填充体体积响应同时存在。后续接触和夹持仍可能留下局部翻转；已交付运行的严格零翻转检查并未通过。','small')


title(6,'共同求解设置与生效说明','复现参数  |  覆盖关系  |  来源')
table(['参数','实际数值'],[
('引擎 / 材料配置','Genesis 1.4.3 / plush_cotton'),
('重力','[0, 0, −9.81] m/s²'),
('主时间步','0.01 s'),
('子步数量 / 子步时长','10 / 0.001 s'),
('PBD 粒子接触直径','0.004 m = 4 mm'),
('拉伸 / 体积 / 弯曲迭代','10 / 10 / 4'),
('全局线性阻力','1 s⁻¹；加速度为 −v'),
('全局二次阻力','0；棉布另有面积加权空气阻力'),
('空间哈希周期尺寸 / 单元尺寸','0.32 m / 0.005 m'),
('数值精度 / 随机种子','float32 / 7'),
],[.46,.54])
para('熊和布的内部阻尼保留自由节点集合的刚体运动模式；全局线性阻力仍会耗散整体运动。因此不能把所有阻尼都描述为保持平移与旋转。','small')
section('配置文件中保留、但已被覆盖的值')
table(['旧值或初始值','当前实际生效方式'],[
('熊 volume_compliance = 1e-12\nvolume_relaxation = 0.1','由压缩 3 kPa / 膨胀 15 kPa 的新体积模型替代'),
('熊 stretch_compliance = 0.001','逐边覆盖：内部 0.01、表面 0.001 m/N'),
('布 bending_compliance = 1e-5','由 B = 5 × 10⁻⁵ N·m 的二面角弯曲模型替代'),
('布原生统一 air_resistance','由每点 0.5ρCdAᵢ 的面积加权系数替代'),
],[.46,.54])
section('来源与使用范围')
para('配置：config.toml；完整运行记录：runs/plush-cotton-complete-01/report.json。实现：material_response.py、cotton_bending.py、cotton_membrane.py；接触：scene.py、pbd_adapter.py、wrap_contact.py、seam_surface_contact.py、velcro_contact.py。','small')
para('原项目：https://github.com/Chloe-Jinlei/bear_arms_scene\n基准提交：abe0008c9331e1d3d875c73916008af7d612186b','small')
para('本表记录该场景的等效物理近似，尚未经过真实玩偶填充物或棉布试样标定。材料属性与数值求解设置应一起理解；本文件是参数记录，不是全部物理验收通过的证明。','small')

sections=['熊与填充体','棉布','魔术贴','刚体与摩擦','附加接触','求解与来源']
def page_decor(canvas,doc):
 canvas.saveState()
 canvas.setStrokeColor(TEAL); canvas.setLineWidth(2);canvas.line(margin,H-30,W-margin,H-30)
 canvas.setFont('Latin',7.2);canvas.setFillColor(MUTED);canvas.drawString(margin,H-23,'ROBOT LEARNING  /  MATERIAL PARAMETER RECORD')
 canvas.setLineWidth(.5);canvas.setStrokeColor(LINE);canvas.line(margin,34,W-margin,34)
 canvas.setFont('Latin',7);canvas.setFillColor(MUTED);canvas.drawString(margin,21,'plush_cotton  |  2026-10-27')
 canvas.drawRightString(W-margin,21,f'{doc.page} / 6')
 canvas.restoreState()
doc=SimpleDocTemplate(str(OUT),pagesize=A4,rightMargin=margin,leftMargin=margin,topMargin=45,bottomMargin=45,title='熊与棉布物理参数设置 - plush_cotton',author='Codex',subject='2026-10-27 版本实际生效的材料、接触和数值求解参数',pageCompression=1)
doc.build(story,onFirstPage=page_decor,onLaterPages=page_decor)
reader=PdfReader(OUT)
texts=[page.extract_text() for page in reader.pages]
assert len(texts)==6, f'Expected 6 pages, got {len(texts)}'
for i,head in enumerate(['熊与棉布物理参数设置','棉布参数','魔术贴参数','桌面、地面与机械臂','附加接触与防翻转设置','共同求解设置与生效说明']):
 assert head in texts[i], (i,head)
combined='\n'.join(texts)
for token in ['3000','15000','0.49','180','29.39','0.45','15 mm','0.08','0.001','24','92','0.25 mm','0.7','0.8','0.9','1.225']:
 assert token in combined,token
(BASE/'tmp/pdfs/extracted.txt').write_text(combined)
print(f'Created: {OUT}\nPages: {len(texts)}\nBytes: {OUT.stat().st_size}')
