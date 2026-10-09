"""Build world_inland.yaml — inland waterways outside Europe. Every number cites a source.
ft->m at 0.3048, 1 decimal; US short ton -> t at 0.9072; hp -> kW at 0.7457."""
from pathlib import Path

import yaml

FT = 0.3048
def m(ft): return round(ft * FT, 1)
def st(short_tons): return round(short_tons * 0.90718)
def kw(hp): return round(hp * 0.7457)

def RV(name, source, **kw_):
    base = dict(name=name, imo_or_eni=None, built=None, yard="", loa_m=None, beam_m=None,
                draught_m=None, depth_m=None, dwt_t=None, teu=None, cargo_capacity_m3=None,
                lightship_t=None, steel_weight_t=None, installed_power_kw=None, propulsion=None,
                service_speed_kn=None, crew=None, source=source)
    base.update(kw_)
    return base

def C(id, family, region, formation, cargo_modes, source, confidence, notes="", refs=None, **kw_):
    base = dict(id=id, family=family, region=region, waters="inland", formation=formation,
                cargo_modes=cargo_modes, loa_m=None, beam_m=None, draught_m=None, air_draft_m=None,
                dwt_t=None, teu=None, n_abreast=1, n_in_line=1, source=source,
                confidence=confidence, notes=notes, reference_vessels=refs or [])
    base.update(kw_)
    # keep key order stable
    order = ["id","family","region","waters","formation","cargo_modes","loa_m","beam_m","draught_m",
             "air_draft_m","dwt_t","teu","n_abreast","n_in_line","source","confidence","notes",
             "reference_vessels"]
    return {k: base[k] for k in order}

S = {
 "siemens": "https://myshare-cms.siemens.com/size-of-barge (secondary aggregator page, read via search summary only)",
 "omb16478": "https://www.oceanmarine.com/vessels/16478/pdf/view (Ocean Marine Brokerage listing #16478, PDF read)",
 "kirby_rct12": "https://vesselinfo.kirbycorp.com/BargeInfo/Details/55665 (Kirby vessel-info page; read via search summary, site refused direct fetch)",
 "kirby_tank": "https://vesselinfo.kirbycorp.com/BargeInfo/Details/220651 and /73639 (Kirby vessel-info pages; read via search summary, site refused direct fetch)",
 "mr1994": "https://magazines.marinelink.com/Magazines/MaritimeReporter/199406/page/14 (Maritime Reporter, June 1994, p12)",
 "umr_locks": "https://www.farmprogress.com/tv-and-radio/lock-and-dam-25-funding-clears-major-hurdle-in-congress ; https://en.wikipedia.org/wiki/Melvin_Price_Locks_and_Dam (search summaries)",
 "cbc_tb": "https://www.workboat.com/news/shipbuilding/conrad-delivers-6000-hp-towboat-to-canal-barge/",
 "acbl": "https://professionalmariner.com/acbl-christens-most-powerful-towboat-on-mississippi-river/",
 "kieffer": "https://www.workboat.com/news/shipbuilding/master-marine-delivers-z-drive-towboat/ (search summary)",
 "troy": "https://www.marinelog.com/inland-coastal/inland/maritime-partners-welcomes-m-v-troy-bernier-to-its-fleet/ (search summary)",
 "dalles": "https://www.asce.org/about-civil-engineering/history-and-heritage/historic-landmarks/the-dalles-lock-and-dam (search summary)",
 "pianc141": "PIANC WG 141 (2019) Table 2.3 p16 + Table A.2 p163, as transcribed in src/vessel_designer/core/vessel_standards.py",
 "gb50139": "GB 50139-2014 Navigation Standard of Inland Waterway, class tonnage list via https://www.chinabaogao.com/free/202606/801029.html (search summary; standard text not read)",
 "gezhouba": "https://www.bairdmaritime.com/shipping/dry-cargo/bulkers/chinese-builder-delivers-electric-inland-bulk-carrier ; https://www.hellenicshippingnews.com/chinas-largest-all-electric-bulk-carrier-launched-in-central-china/",
 "cjsr7500": "https://www.researching.cn/articles/OJ3c6081a53ee288df/figureandtable (Chinese Journal of Ship Research; read via search summary only, site TLS failed)",
 "iwai_wiki": "https://en.wikipedia.org/wiki/Inland_Waterways_Authority_of_India (classification table; uncited on Wikipedia; IWAI primary notification not read)",
 "iwai_dst": "https://www.ship-technology.com/news/iwai-unveils-13-ship-designs-large-barge-haulage/ ; https://www.maritimeprofessional.com/amp/news/inland-waterways-authority-india-releases-321073 (table read via search summary only)",
 "volga_r156": "https://www.volgaflot.com/en/fleet/river/project-r156/ (Volga Shipping fleet page)",
 "volga_ot2000": "https://www.volgaflot.com/en/fleet/river/ot-2000/",
 "volga_ot2400": "https://www.volgaflot.com/en/fleet/river/ot-2400/",
 "volga_vd": "https://www.volgaflot.com/en/fleet/river/volgo-don/",
 "meb507b": "https://mebspb.com/drye/507Be.html (Marine Engineering Bureau, Project 507B modernisation)",
 "vdcanal": "https://en.wikipedia.org/wiki/Volga%E2%80%93Don_Canal",
 "volgoneft": "https://en.wikipedia.org/wiki/Volgoneft",
 "p00443": "https://seanews.ru/en/2025/02/17/en-new-pusher-tug-concept-developed",
 "hidro_mm": "https://mundomaritimo.cl/noticias/convoyes-de-barcazas-de-290-por-60-metros-en-hidrovia-paraguay-parana-adicionarian-volumen-de-carga-de-12000-toneladas",
 "hidro_bo": "https://www.boletinoficial.gob.ar/pdf/linkQR/eDdRRVpjVUZ6TXcrdTVReEh2ZkU0dz09 (Argentine Boletín Oficial; read via search summary only)",
 "hbsa_py": "https://www.bairdmaritime.com/tugs/new-push-boats-and-barges-for-paraguay",
 "hbsa_amz": "https://www.bairdmaritime.com/tugs/inland-tug-operations/hidrovias-do-brasils-newest-river-tugs-begin-operations",
 "amz_ms": "https://maritimesouth.com/2021/04/23/the-battle-for-higher-convoy-efficiency-in-the-amazonian-inland-waterways/",
 "tiete": "https://semil.sp.gov.br/htp/wp-content/uploads/sites/13/2024/02/Anexo-Plano-Diretor-Hidrovia-Tiete-Comboios-jun2021.pdf (Plano Diretor da Hidrovia Tietê-Paraná Vol I, Depto Hidroviário SP, pp13-15)",
 "transtrack": "https://transtrack.co/blog/barges-2/ (Indonesian logistics vendor blog — secondary)",
 "barlian": "https://www.scribd.com/doc/264487738/barge-built (read via search summary only)",
 "ktu300": "https://www.scribd.com/doc/79585735/Barge-Specification (read via search summary only)",
 "macgregor": "https://www.macgregor.com/globalassets/picturepark/imported-assets/71758.pdf (MacGregor case sheet, PDF text read)",
 "patria22": "https://www.bairdmaritime.com/work-boat-world/tug-and-salvage-world/inland-tug-operations/vessel-review-patria-22-shallow-draught-barge-handling-tug-designed-for-indonesias-barito-river",
 "nongsa": "https://www.cummins.com/en-eu/case-studies/nongsa-jaya-buana-tugs-all-jobs (read via search summary only; direct fetch 403)",
 "argus_barito": "https://www.argusmedia.com/en/news-and-insights/latest-market-news/2869712-barito-river-bottleneck-hits-indonesian-coal-flows (search summary)",
 "sxcoal_mahakam": "https://en.sxcoal.com/news/detail/2097489163615506433 (search summary)",
 "mekong": "https://archive.iwlearn.net/mrcmekong.org/RAK/html/1.15.2_river_transportation.html ; https://www.unescap.org/sites/default/d8files/event-documents/14-Cambodia.pdf (search summary)",
 "nile_asy": "https://alexyard.com.eg/?p=2130 (Alexandria Shipyard project page)",
 "nile_national": "https://www.thenationalnews.com/business/signs-of-a-revival-on-the-nile-1.507493 (search summary)",
 "congo": "https://www.vliz.be/imisdocs/publications/ocrd/375261.pdf ; https://www.visapourlimage.com/en/festival/exhibitions/fleuve-congo (search summaries)",
 "volta": "https://thebftonline.com/2023/03/20/vltc-boss-calls-for-government-intervention-highlights-advantages-of-volta-lake-transport/ ; https://gna.org.gh/?p=266221 (search summaries)",
 "niwa": "https://shippingposition.com.ng/niwa-licenses-eight-companies-for-barge-operations-md/ ; https://gazettengr.com/niwa-begins-transportation-activities-on-river-niger/ (search summaries)",
 "berbice": "https://www.oldendorff.com/pages/transshipment/guyana (search-index text; current page no longer shows it) ; https://boskalis.com/media/52cjvkee/guyana_-_the_berbice_river_project.pdf",
 "bosai": "https://pubs.usgs.gov/myb/vol3/2016/myb3-2016-guyana.pdf (USGS Minerals Yearbook 2016 Guyana; search summary)",
 "trombetas": "https://www.swedishclub.com/uploads/2023/12/AMAZON-CIRCULAR-NOVEMBER-2017.pdf (search summary)",
}

classes = []

# ---------------- USA ----------------
classes += [
 C("US-STD-HOPPER-175", "US-inland", "americas-inland", "pushed_barge", ["dry_bulk"],
   S["siemens"], "low",
   notes="Brief names 175x26 ft (53.3x7.9 m) as the old 'standard' barge; NOT confirmed by any source read. "
         "The only source found gives 175x35 ft (53.3x10.7 m) at ~1,000 tons. Kept as a placeholder; "
         "dims below are the sourced 175x35 ft variant.",
   loa_m=m(175), beam_m=m(35), dwt_t=st(1000)),
 C("US-JUMBO-HOPPER", "US-inland", "americas-inland", "pushed_barge", ["dry_bulk"],
   S["siemens"] + " ; " + S["mr1994"] + " ; " + S["hidro_mm"], "medium",
   notes="195x35 ft (59.4x10.7 m), depth 10-14 ft (3.0-4.3 m), 9 ft (2.7 m) draught, 1,500 short tons "
         "(=1,361 t); typical light weight ~300 short tons (=272 t) per the aggregator page (low). "
         "Upper-Miss 600x110 ft lock takes 3 abreast. Same unit is the Paraná 'Mississippi barge' (60x11 m, 1,600 t).",
   loa_m=m(195), beam_m=m(35), draught_m=[2.7, 2.7], dwt_t=st(1500),
   refs=[RV("RCT 12 (covered hopper)", S["kirby_rct12"], built=1997, yard="Jeffboat",
            loa_m=m(195), beam_m=m(35), depth_m=m(12), draught_m=m(9), dwt_t=st(1158)),
         ]),
 C("US-STRETCH-HOPPER-200", "US-inland", "americas-inland", "pushed_barge", ["dry_bulk"],
   S["omb16478"], "medium",
   notes="200x35x12 ft (61.0x10.7x3.7 m) open hopper. Light draught 2.6 ft (0.79 m) from broker sheet — "
         "a usable lightship proxy (displacement at 0.79 m ~ L*B*T*Cb). The broker's metric conversions are wrong; "
         "use the ft values.",
   loa_m=m(200), beam_m=m(35),
   refs=[RV("Open hopper barge (12 sisters, broker #16478)", S["omb16478"], built=2003,
            loa_m=m(200), beam_m=m(35), depth_m=m(12), draught_m=None)]),
 C("US-SUPER-JUMBO-HOPPER", "US-inland", "americas-inland", "pushed_barge", ["dry_bulk"],
   S["mr1994"], "high",
   notes="Trinity Marine 260x52.5 ft (79.2x16.0 m). 3,350 short tons (=3,039 t) coal per barge at 9.5 ft (2.9 m). "
         "Two abreast fit 110 ft locks.",
   loa_m=m(260), beam_m=m(52.5), draught_m=[2.9, 2.9], dwt_t=st(3350),
   refs=[RV("Trinity Super Jumbo hopper (first series)", S["mr1994"], yard="Trinity Marine, Madisonville LA",
            loa_m=m(260), beam_m=m(52.5), draught_m=m(9.5), dwt_t=st(3350))]),
 C("US-TANK-BARGE-297", "US-inland", "americas-inland", "pushed_barge", ["liquid_bulk"],
   S["kirby_tank"] + " ; " + S["siemens"], "medium",
   notes="297.5x54 ft (90.7x16.5 m), depth ~12 ft (3.7 m). ~29,000-30,000 bbl; ~2,360 tons at 7 ft (2.1 m) to "
         "3,800+ tons at 10+ ft (3.0 m) (Kirby, units probably short tons). Aggregator gives light weight "
         "~1,000 short tons (=907 t) — low confidence; check against a Kirby light-draught line.",
   loa_m=m(297.5), beam_m=m(54), draught_m=[2.1, 3.0], dwt_t=[st(2360), st(3800)]),
 C("US-TOWBOAT-2000HP", "US-inland", "americas-inland", "towboat", ["dry_bulk", "liquid_bulk"],
   S["kieffer"] + " ; " + S["troy"], "medium",
   notes="Harbour/fleeting and small-line band, 78-84 x 34 ft (23.8-25.6 x 10.4 m), 1,800-2,600 hp (1,342-1,939 kW).",
   loa_m=[m(78), m(84)], beam_m=m(34),
   refs=[RV("Kieffer E. Bailey", S["kieffer"], yard="Master Marine, Bayou La Batre AL", loa_m=m(78), beam_m=m(34),
            depth_m=m(11), installed_power_kw=kw(2000), propulsion="diesel"),
         RV("Troy Bernier", S["troy"], yard="C&C Marine & Repair, Belle Chasse LA", loa_m=m(84), beam_m=m(34),
            depth_m=m(11), installed_power_kw=kw(2600), propulsion="diesel")]),
 C("US-TOWBOAT-6000HP", "US-inland", "americas-inland", "towboat", ["dry_bulk", "liquid_bulk"],
   S["cbc_tb"], "high", notes="Line-haul band (Ohio/Upper Miss/GIWW).",
   refs=[RV("H. Merritt 'Heavy' Lane Jr.", S["cbc_tb"], built=2020, yard="Conrad Shipyard (Amelia), LA",
            loa_m=m(166), beam_m=m(49), depth_m=round((12+4/12)*FT, 1), draught_m=round(10.5*FT, 1),
            installed_power_kw=4476, propulsion="diesel")]),
 C("US-TOWBOAT-11000HP", "US-inland", "americas-inland", "towboat", ["dry_bulk"],
   S["acbl"], "high", notes="Lower-Miss line-haul. ACBL Mariner pushes up to 64 barges (>75,000 tons).",
   refs=[RV("ACBL Mariner", S["acbl"], built=2024, yard="C&C Marine & Repair, Belle Chasse LA",
            loa_m=m(200), beam_m=m(50), installed_power_kw=kw(11000), propulsion="diesel")]),
 C("US-UMR-15-TOW", "US-inland", "americas-inland", "pushed_convoy", ["dry_bulk"],
   S["umr_locks"], "medium",
   notes="Upper Miss limit 15 barges (3 abreast x 5 long of 195x35 ft). Barge train 975x105 ft (297.2x32.0 m) "
         "DERIVED from unit size, excludes towboat. 600x110 ft (182.9x33.5 m) chambers force a double lockage; "
         "1,200 ft (365.8 m) chambers pass it whole. DWT derived: 15 x 1,361 t.",
   loa_m=297.2, beam_m=32.0, draught_m=[2.7, 2.7], dwt_t=15*st(1500), n_abreast=3, n_in_line=5),
 C("US-LMR-LARGE-TOW", "US-inland", "americas-inland", "pushed_convoy", ["dry_bulk"],
   S["acbl"], "medium",
   notes="Lock-free Lower Miss: 40+ barges common; ACBL Mariner rated for 64 barges / >75,000 tons. Geometry varies.",
   dwt_t=st(75000)),
 C("US-LOCK-600x110", "US-inland", "americas-inland", "pushed_convoy", ["dry_bulk", "liquid_bulk"],
   S["umr_locks"], "medium", notes="Envelope: most UMR primary chambers 600x110 ft.",
   loa_m=m(600), beam_m=m(110)),
 C("US-LOCK-1200x110", "US-inland", "americas-inland", "pushed_convoy", ["dry_bulk", "liquid_bulk"],
   S["umr_locks"], "medium", notes="Envelope: Melvin Price main chamber 1,200x110 ft; lift 15 ft.",
   loa_m=m(1200), beam_m=m(110)),
 C("US-COLUMBIA-SNAKE-LOCK", "US-inland", "americas-inland", "pushed_convoy", ["dry_bulk"],
   S["dalles"], "medium",
   notes="Envelope: standard Columbia-Snake chamber 86x675 ft; sized for a tug + 4-5 grain barges. Barge dims not found.",
   loa_m=m(675), beam_m=m(86)),
]

# ---------------- China ----------------
cn = [
 ("CN-I-MOTOR", "motor_vessel", 95.0, 16.2, 3.2, 3000, 1, 1),
 ("CN-II-MOTOR", "motor_vessel", 90.0, 14.8, 2.6, 2000, 1, 1),
 ("CN-III-MOTOR", "motor_vessel", 85.0, 10.8, 2.0, 1000, 1, 1),
 ("CN-IV-MOTOR", "motor_vessel", 67.5, 10.8, 1.6, 500, 1, 1),
 ("CN-I-CONVOY-2x2", "pushed_convoy", 223.0, 32.4, 3.5, 12000, 2, 2),
 ("CN-II-CONVOY-2x2", "pushed_convoy", 186.0, 32.4, 2.6, 8000, 2, 2),
 ("CN-III-CONVOY-2x2", "pushed_convoy", 167.0, 21.6, 2.0, 4000, 2, 2),
]
for id_, f, L, B, T, D, na, nl in cn:
    note = "Reused from vessel_standards.py (PIANC WG 141 Table 2.3). Class I is the LARGEST."
    if f == "pushed_convoy":
        note += " Convoy DWT is INFERRED (4 x unit DWT); WG 141 does not tabulate it."
    classes.append(C(id_, "CN-GB50139", "asia-inland", f, ["dry_bulk"], S["pianc141"],
                     "high" if f == "motor_vessel" else "medium", notes=note,
                     loa_m=L, beam_m=B, draught_m=[T, T], dwt_t=D, n_abreast=na, n_in_line=nl))
for cls, d in (("V", 300), ("VI", 100), ("VII", 50)):
    classes.append(C(f"CN-{cls}", "CN-GB50139", "asia-inland", "motor_vessel", ["dry_bulk"], S["gb50139"],
                     "medium", notes=f"GB 50139-2014 class {cls} = {d} t vessel. Dimensions NOT found; standard text not read.",
                     dwt_t=d))
classes.append(C("CN-YANGTZE-130-THREE-GORGES", "CN-Yangtze-standard", "asia-inland", "motor_vessel",
   ["dry_bulk"], S["gezhouba"] + " ; " + S["cjsr7500"], "medium",
   notes="Yangtze trunk / Three Gorges lock '130 m class' standard ship type (GB/T 23432-2009 dimension series; "
         "standard text not read). Beam ~16.2-16.3 m lets two ships lie abreast in the 34 m-wide Three Gorges "
         "chamber (chamber width from general knowledge, not verified this pass). A 7,500 t design: LWL 130, "
         "LPP 128, B 16.2, D 7.2, T 5.2 m (CJSR, low).",
   loa_m=[128.0, 130.0], beam_m=16.2, draught_m=[5.2, 5.2], dwt_t=[7500, 10000],
   refs=[RV("Gezhouba (all-electric bulk carrier)", S["gezhouba"], built=2025, yard="Yichang Zigui Huaxing Shipyard",
            loa_m=129.9, dwt_t=10000, propulsion="electric"),
         RV("7,500 t Yangtze bulk carrier design (CJSR table)", S["cjsr7500"], loa_m=130.0, beam_m=16.2,
            depth_m=7.2, draught_m=5.2, dwt_t=7500)]))

# ---------------- India ----------------
iwai = [  # class, (dwt_sp, L_sp), (dwt_cv, L_cv, B_cv, abreast,inline), B_sp, T, air
 (1, 100, 32, 200, 80, 5, 1, 2, 5, 1.0, 4),
 (2, 300, 45, 600, 110, 8, 1, 2, 8, 1.2, 5),
 (3, 500, 58, 1000, 141, 9, 1, 2, 9, 1.5, 6),
 (4, 1000, 70, 2000, 170, 12, 1, 2, 12, 1.8, 7),
 (5, 1000, 70, 4000, 170, 24, 2, 2, 12, 1.8, 10),
 (6, 2000, 86, 4000, 210, 14, 1, 2, 14, 2.5, 10),
 (7, 2000, 86, 8000, 210, 28, 2, 2, 14, 2.5, 10),
]
for c, dsp, Lsp, dcv, Lcv, Bcv, na, nl, Bsp, T, air in iwai:
    refs = []
    if c == 6:
        refs = [RV("IWAI/DST standard design — dry bulk carrier type 2 (NW-1)", S["iwai_dst"], loa_m=110.0,
                   beam_m=12.0, draught_m=2.8, depth_m=4.3, dwt_t=2515, installed_power_kw=900,
                   propulsion="diesel", service_speed_kn=7.0)]
    classes.append(C(f"IN-IWAI-{c}-MOTOR", "IN-IWAI", "asia-inland", "motor_vessel", ["dry_bulk"],
                     S["iwai_wiki"], "medium", notes="Self-propelled variant of IWAI class." +
                     (" DST design (110x12x2.8 m, 2,515 t) sits between class 4 beam and class 6 draught — "
                      "a 2x500 kW plant quoted with 'total 900 kW' (source inconsistency); 13 km/h." if c == 6 else ""),
                     loa_m=Lsp, beam_m=Bsp, draught_m=[T, T], air_draft_m=air, dwt_t=dsp, refs=refs))
    classes.append(C(f"IN-IWAI-{c}-CONVOY", "IN-IWAI", "asia-inland", "pushed_convoy", ["dry_bulk"],
                     S["iwai_wiki"], "medium", notes=f"Tug + {na*nl} barges ({na} abreast x {nl} long).",
                     loa_m=Lcv, beam_m=Bcv, draught_m=[T, T], air_draft_m=air, dwt_t=dcv, n_abreast=na, n_in_line=nl))

# ---------------- Russia ----------------
classes += [
 C("RU-R156-PUSHED-BARGE", "RU-RRR", "russia-inland", "pushed_barge", ["dry_bulk"], S["volga_r156"], "high",
   notes="Russian River Register class O 2.0 (Ice 20) (O = 2.0 m wave category). Head and end sections; "
         "forms single/twin/triple trains of 9,000-18,000 t.",
   loa_m=[114.45, 114.6], beam_m=14.24, draught_m=[3.7, 3.7], dwt_t=[4500, 4575],
   refs=[RV("Project R156 head section", S["volga_r156"], yard="", loa_m=114.6, beam_m=14.24, draught_m=3.7, dwt_t=4500),
         RV("Project R156 end section", S["volga_r156"], loa_m=114.45, beam_m=14.24, draught_m=3.7, dwt_t=4575)]),
 C("RU-PUSHER-OT2000-2400", "RU-RRR", "russia-inland", "pusher", ["dry_bulk"],
   S["volga_ot2000"] + " ; " + S["volga_ot2400"] + " ; " + S["p00443"], "high",
   notes="~140 OT-2000/OT-2400 (Hungarian-built) still in service, 35-56 years old. 'Depth overall' on the "
         "operator pages (15.75 / 14.36 m) is height to top of wheelhouse, i.e. air draught, not hull depth.",
   loa_m=[45.4, 51.6], beam_m=12.0, draught_m=[2.25, 2.3],
   refs=[RV("OT-2000 (Project 428)", S["volga_ot2000"], loa_m=45.4, beam_m=12.0, draught_m=2.25,
            installed_power_kw=1470, propulsion="diesel"),
         RV("OT-2400 (Project N3290)", S["volga_ot2400"], loa_m=51.6, beam_m=12.0, draught_m=2.3,
            installed_power_kw=1766, propulsion="diesel"),
         RV("Design 00443 (concept replacement)", S["p00443"], loa_m=47.0, beam_m=14.0, depth_m=3.5,
            draught_m=2.3, installed_power_kw=2000, propulsion="diesel", crew="10-12")]),
 C("RU-R156-TRAIN-4", "RU-RRR", "russia-inland", "pushed_convoy", ["dry_bulk"], S["p00443"] + " ; " + S["volga_r156"],
   "medium", notes="00443 pusher designed for 'four-vessel' trains of 18,000 t (4 x R156-size barges). Geometry not stated.",
   dwt_t=18000),
 C("RU-VOLGO-DON-5000", "RU-RRR", "russia-inland", "motor_vessel", ["dry_bulk"], S["volga_vd"] + " ; " + S["meb507b"],
   "high", notes="Projects 1565/507B. River Register classes M 2.0/2.5, O-PR 2.0, M-PR 2.5 (overlaps river-sea slice). "
                 "Hold volume conflict: operator 6,320 m3 vs MEB 507B-modernised 9,360 m3.",
   loa_m=[138.3, 138.74], beam_m=16.7, draught_m=[3.5, 3.6], dwt_t=[5000, 5290],
   refs=[RV("Volgo-Don (Volga Shipping series, Pr 1565/507B)", S["volga_vd"], loa_m=138.3, beam_m=16.7,
            draught_m=3.5, dwt_t=5000, cargo_capacity_m3=6320),
         RV("Project 507B modernised", S["meb507b"], loa_m=138.74, beam_m=16.7, depth_m=5.5, draught_m=3.6,
            dwt_t=5290, cargo_capacity_m3=9360, installed_power_kw=1324, propulsion="diesel",
            service_speed_kn=10.0, crew=14)]),
 C("RU-VOLGA-DON-CANAL-MAX", "RU-RRR", "russia-inland", "motor_vessel", ["dry_bulk", "liquid_bulk"], S["vdcanal"],
   "medium", notes="Envelope: smallest Volga-Don canal lock 145x17 m, 3.6 m; 13 locks; max ship 141x16.8x3.6 m, ~5,000 t.",
   loa_m=141.0, beam_m=16.8, draught_m=[3.6, 3.6], dwt_t=5000),
 C("RU-VOLGONEFT-TANKER", "RU-RRR", "russia-inland", "motor_vessel", ["liquid_bulk"], S["volgoneft"], "medium",
   notes="Soviet Volga/canal tankers (Pr 558/550/1577/550A/630). Draught and DWT not given in source.",
   loa_m=[132.6, 137.81], beam_m=[16.9, 17.0],
   refs=[RV("Volgoneft Pr 550/1577/550A", S["volgoneft"], loa_m=132.6, beam_m=16.9, depth_m=5.5,
            installed_power_kw=1472, propulsion="diesel"),
         RV("Volgoneft Pr 630", S["volgoneft"], yard="Ivan Dimitrov / Ruse Shipyard, Bulgaria", loa_m=137.81,
            beam_m=17.0, depth_m=6.4, installed_power_kw=1764, propulsion="diesel")]),
]

# ---------------- South America ----------------
classes += [
 C("SA-HIDROVIA-MISSISSIPPI-BARGE", "SA-Hidrovia", "americas-inland", "pushed_barge", ["dry_bulk"], S["hidro_mm"],
   "medium", notes="Paraná-Paraguay 'Mississippi' barge 60x11 m, 1,600 t.", loa_m=60.0, beam_m=11.0, dwt_t=1600),
 C("SA-HIDROVIA-JUMBO-BARGE", "SA-Hidrovia", "americas-inland", "pushed_barge", ["dry_bulk"],
   S["hidro_mm"] + " ; " + S["hbsa_py"], "medium",
   notes="'Jumbo' 60x16 m, 1,500-2,600 t (source wording ambiguous). HBSA iron-ore hoppers 61x15x4.27 m, 2,500 dwt "
         "(box mid-convoy + raked ends).",
   loa_m=[60.0, 61.0], beam_m=[15.0, 16.0], dwt_t=[1500, 2600],
   refs=[RV("HBSA Mississippi-style hopper (144 built)", S["hbsa_py"], built=2014, yard="ZPMC, China",
            loa_m=61.0, beam_m=15.0, depth_m=4.27, dwt_t=2500)]),
 C("SA-HIDROVIA-CONVOY-290x50", "SA-Hidrovia", "americas-inland", "pushed_convoy", ["dry_bulk"],
   S["hidro_mm"] + " ; " + S["hidro_bo"], "medium",
   notes="Authorised San Lorenzo-Nueva Palmira, 24,000 t. 4x4 Mississippi barges at 1,500 t need >= 4,114 hp "
         "(3,068 kW) installed (Boletín Oficial, via summary). Proposed 290x60 m (12 jumbo + 4 Mississippi, 36,000 t) "
         "and 290x65 m.",
   loa_m=290.0, beam_m=50.0, dwt_t=24000, n_abreast=4, n_in_line=4),
 C("SA-PARAGUAY-4x4-HBSA", "SA-Hidrovia", "americas-inland", "pushed_convoy", ["dry_bulk"], S["hbsa_py"], "high",
   notes="16 x 2,500 t hoppers, ~40,000 t per shipment. Pusher draught 2.1 m dry / 2.4 m wet season.",
   dwt_t=40000, n_abreast=4, n_in_line=4,
   refs=[RV("RApide 4500 pusher (8 built)", S["hbsa_py"], built=2014, yard="Uzmar, Turkey", loa_m=46.5,
            beam_m=16.5, draught_m=2.4, propulsion="diesel-electric", crew=18)]),
 C("SA-AMAZON-CONVOY", "SA-Amazon", "americas-inland", "pushed_convoy", ["dry_bulk"], S["amz_ms"] + " ; " + S["hbsa_amz"],
   "medium",
   notes="Madeira/Tapajós/Amazon grain. Mississippi barge 61x10.7 m, 2,000 dwt; local 2,500-3,000 dwt. Convoys "
         "2x3 to 5x5: 20,000-50,000 dwt; TBL 3x5 37,000 dwt (~15 t/kW); HBSA 36-barge 72,000 dwt (~13 t/kW).",
   dwt_t=[20000, 72000],
   refs=[RV("HB Pirarara / HB Pirarucu (pusher)", S["hbsa_amz"], yard="Estaleiro Rio Maguari (Robert Allan design)",
            loa_m=39.6, beam_m=18.0, draught_m=2.8, crew=17)]),
 C("SA-TIETE-BARGE", "SA-Tiete-Parana", "americas-inland", "pushed_barge", ["dry_bulk"], S["tiete"], "high",
   notes="Primary state document. Light weight ~220 t per barge (250 t with steel hatch covers) — a direct "
         "steel-weight calibration point for a 59.4x10.7x3.5 m Mississippi-type hull.",
   loa_m=59.44, beam_m=10.67, draught_m=[2.5, 3.0], dwt_t=1500,
   refs=[RV("Tietê standard chata", S["tiete"], loa_m=59.44, beam_m=10.67, depth_m=3.5, draught_m=3.0,
            dwt_t=1500, lightship_t=220)]),
 C("SA-TIETE-CONVOY-2x2", "SA-Tiete-Parana", "americas-inland", "pushed_convoy", ["dry_bulk"], S["tiete"], "high",
   notes="4 barges + pusher, 138.0x21.7 m, ~6,000 t at up to 2.8 m. Tietê locks ~145x12 m, 2.5 m (approx.) — convoy "
         "splits to pass. Pusher 18.5x8.5 m, T 2.2 m, 800-950 hp. Proposed 9,000 t: 6 barges + bow thruster unit, "
         "~210x21.3x3.0 m.",
   loa_m=138.0, beam_m=21.7, draught_m=[2.5, 2.8], dwt_t=6000, n_abreast=2, n_in_line=2,
   refs=[RV("Tietê standard pusher", S["tiete"], loa_m=18.5, beam_m=8.5, draught_m=2.2,
            installed_power_kw=[kw(800), kw(950)], propulsion="diesel")]),
]

# ---------------- SE Asia ----------------
ind = [(180, None), (230, 4000), (270, 6000), (300, 8000), (330, [10000, 12000])]
for ft, cap in ind:
    refs = []
    note = "Indonesian standard deck/coal barge, named by length in feet. Capacity from vendor blog (secondary)."
    if ft == 180:
        note += " 180 ft units feed upriver legs (e.g. Lok Buntar) and tranship into 300 ft barges. Capacity not found."
    if ft == 230:
        refs = [RV("Barlian 231", S["barlian"], built=2007, yard="Batam", loa_m=m(230), beam_m=m(70),
                   depth_m=m(16), dwt_t=5000)]
        note += " Reference Barlian 231 quoted at 5,000 t — conflicts with the 4,000 t band."
    if ft == 300:
        refs = [RV("300 ft barge, PT Karya Tekhnik Utama", S["ktu300"], built=2008, yard="PT Karya Tekhnik Utama, Batam",
                   loa_m=91.44, beam_m=24.38, depth_m=5.48),
                RV("Patria 22 (tug for 91 m Barito coal barges)", S["patria22"], built=2020,
                   yard="Patria Maritim Perkasa", loa_m=23.6, beam_m=9.2, depth_m=3.0, draught_m=2.0,
                   installed_power_kw=1220, propulsion="diesel", service_speed_kn=12.0)]
        note += (" Beam seen 80-90 ft (24.4-27.4 m). Barito: 'standard 7,500-10,000 t barges, draft ~6.5 m' (Argus) "
                 "— 6.5 m looks like depth, not draught; low water cuts loads to 3,000-4,000 t. Mahakam normal ~7,000 t, "
                 "restricted to 5,500-6,000 t. LOI evidence: 300 ft set = 7,500 t.")
    if ft == 330:
        note += " Dimensions not found."
    classes.append(C(f"ID-BARGE-{ft}FT", "ID-Indonesian-standard", "asia-inland", "towed_barge", ["dry_bulk"],
                     S["transtrack"] + (" ; " + S["argus_barito"] + " ; " + S["sxcoal_mahakam"] if ft == 300 else ""),
                     "medium" if cap else "low", notes=note, loa_m=m(ft), dwt_t=cap, refs=refs))
classes += [
 C("ID-BARGE-250FT", "ID-Indonesian-standard", "asia-inland", "towed_barge", ["dry_bulk"], S["nongsa"], "low",
   notes="250x70 ft (76.2x21.3 m) 4,500 dwt barge towed by a 2x KTA19 tug, 1,200 hp combined (895 kW), ~12 t BP.",
   loa_m=m(250), beam_m=m(70), dwt_t=4500,
   refs=[RV("Nongsa Jaya Buana 1,200 hp tug", S["nongsa"], yard="Nongsa Jaya Buana, Batam",
            installed_power_kw=kw(1200), propulsion="diesel")]),
 C("ID-SELF-UNLOADING-COAL-BARGE", "ID-Indonesian-standard", "asia-inland", "towed_barge", ["dry_bulk"],
   S["macgregor"], "high",
   notes="East Kalimantan coastal transfer (strictly coastal). Two sizes; self-unloading conveyors.",
   loa_m=[79.2, 106.0], beam_m=[20.5, 22.5], draught_m=[3.5, 4.5], dwt_t=[3500, 7000],
   refs=[RV("MacGregor self-unloader 3,500 dwt", S["macgregor"], loa_m=79.2, beam_m=20.5, depth_m=5.6, draught_m=3.5, dwt_t=3500),
         RV("MacGregor self-unloader 7,000 dwt", S["macgregor"], loa_m=106.0, beam_m=22.5, depth_m=6.6, draught_m=4.5, dwt_t=7000)]),
 C("MEKONG-LOWER-ENVELOPE", "Mekong", "asia-inland", "motor_vessel", ["dry_bulk", "container"], S["mekong"], "medium",
   notes="Vietnam border-Phnom Penh: bends limit LOA to ~110 m (~7,000 DWT). Kampong Cam-Phnom Penh: 2,000 DWT "
         "year-round. Phnom Penh-Vam Nao: 3,000-4,000 DWT low water, 5,000 mean-high. Tonle Sap: 1,000/2,000 DWT. "
         "Up to Kratie: 150 t boats.",
   loa_m=110.0, dwt_t=[2000, 7000]),
]

# ---------------- Africa / Guiana Shield ----------------
classes += [
 C("AF-NILE-SELF-PROPELLED-BARGE", "Nile-NNCRT", "africa-inland", "motor_vessel", ["dry_bulk"],
   S["nile_asy"] + " ; " + S["nile_national"], "medium",
   notes="Cairo-Aswan. Capacity up to 1,600 t (The National). ASY lists 16 kn — implausible for 600 hp; treat as error.",
   loa_m=100.2, beam_m=11.2, draught_m=[2.2, 2.2], dwt_t=1600,
   refs=[RV("NNCRT self-propelled barge (6 built)", S["nile_asy"], yard="Alexandria Shipyard", loa_m=100.2,
            beam_m=11.2, draught_m=2.2, installed_power_kw=kw(600), propulsion="diesel", crew=9)]),
 C("AF-CONGO-CONVOY", "Congo-SCTP", "africa-inland", "pushed_convoy", ["general", "dry_bulk"], S["congo"], "low",
   notes="ONATRA/SCTP barges: PG 800 (800 t), 1,000 t and 500 t types. Kotakoli convoy: 8 barges two-by-two, "
         "~200x30 m, >5,000 t.",
   loa_m=200.0, beam_m=30.0, dwt_t=5000, n_abreast=2, n_in_line=4),
 C("AF-VOLTA-LAKE-BARGE", "Volta-VLTC", "africa-inland", "pushed_barge", ["dry_bulk", "liquid_bulk"], S["volta"], "low",
   notes="Akosombo-Buipe. VLTC: 3 bulk barges of 2,250 t; 6 more totalling 4,676 t; one tug moves up to 9 barges. "
         "No dimensions found. Highest-priority gap for a Ghana bauxite/manganese tool.",
   dwt_t=2250),
 C("AF-NIGER-BENUE-BARGE", "Niger-NIWA", "africa-inland", "towed_barge", ["dry_bulk"], S["niwa"], "low",
   notes="NIWA procured 500, 800 and 1,000 t dump barges; Lagos-Onitsha barge licences. No dimensions found.",
   dwt_t=[500, 1000]),
 C("SA-GUYANA-BERBICE-BAUXITE-BARGE", "Guyana-bauxite", "americas-inland", "towed_barge", ["dry_bulk"],
   S["berbice"] + " ; " + S["bosai"], "low",
   notes="Aroaima mine to Berbice mouth, 240 km: 20 purpose-built covered barges of 3,000 tdw + 6 tugs, 1-3 Mtpa, "
         "transhipped by floating crane. Bosai (Linden, Demerara) ships 5,000-6,000 t lots to New Amsterdam. "
         "Trombetas (Brazil) is NOT a barge case: MRN loads ocean ships direct at Porto Trombetas "
         "(max LOA 245 m, B 40 m, sailing draught 11.58 m).",
   dwt_t=3000),
]

with open(Path(__file__).with_name("world_inland.yaml"), "w") as f:
    f.write("# World inland waterways outside Europe — calibration catalogue. Built by build_world_inland.py, 2026-10-06.\n"
            "# Units: m, t (metric). US short tons converted x0.90718; hp x0.7457. Every figure cites `source`.\n")
    yaml.safe_dump({"classes": classes}, f, sort_keys=False, allow_unicode=True, width=120)
nref = sum(len(c["reference_vessels"]) for c in classes)
print(len(classes), "classes,", nref, "reference vessels")
