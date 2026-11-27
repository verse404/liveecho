"""Smart Chinese concert/festival/approval parser, 12306 rail planner, refund/return sniper, and stub stats."""

from __future__ import annotations

import collections
import datetime
import re
from typing import Any
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

REGION_LABELS: dict[str, str] = {
    "all": "全国全部",
    "jzh": "江浙沪皖",
    "jjj": "京津冀",
    "gba": "广深港澳",
    "cy": "川渝西南",
    "central": "华中地区",
    "fujian": "闽台海西",
    "north_nw": "北方/西北",
    "other": "其他城市",
}

CITY_TO_REGION: dict[str, str] = {
    # 江浙沪皖
    "上海": "jzh",
    "杭州": "jzh",
    "南京": "jzh",
    "苏州": "jzh",
    "宁波": "jzh",
    "无锡": "jzh",
    "常州": "jzh",
    "嘉兴": "jzh",
    "绍兴": "jzh",
    "温州": "jzh",
    "金华": "jzh",
    "湖州": "jzh",
    "南通": "jzh",
    "扬州": "jzh",
    "徐州": "jzh",
    "合肥": "jzh",
    "芜湖": "jzh",
    "阜阳": "jzh",
    "蚌埠": "jzh",
    "马鞍山": "jzh",
    "安庆": "jzh",
    "滁州": "jzh",
    # 京津冀
    "北京": "jjj",
    "天津": "jjj",
    "石家庄": "jjj",
    "保定": "jjj",
    "秦皇岛": "jjj",
    "廊坊": "jjj",
    # 广深港澳 + 华南
    "广州": "gba",
    "深圳": "gba",
    "佛山": "gba",
    "东莞": "gba",
    "珠海": "gba",
    "中山": "gba",
    "惠州": "gba",
    "江门": "gba",
    "香港": "gba",
    "澳门": "gba",
    "南宁": "gba",
    "桂林": "gba",
    "柳州": "gba",
    "北海": "gba",
    "海口": "gba",
    "三亚": "gba",
    "澄迈": "gba",
    "万宁": "gba",
    "陵水": "gba",
    # 川渝西南
    "成都": "cy",
    "重庆": "cy",
    "昆明": "cy",
    "贵阳": "cy",
    "大理": "cy",
    "丽江": "cy",
    # 华中
    "武汉": "central",
    "长沙": "central",
    "郑州": "central",
    "南昌": "central",
    "景德镇": "central",
    "宜昌": "central",
    "洛阳": "central",
    # 闽台
    "厦门": "fujian",
    "福州": "fujian",
    "泉州": "fujian",
    "台北": "fujian",
    "高雄": "fujian",
    "台中": "fujian",
    "台南": "fujian",
    # 北方 / 西北 / 东北
    "西安": "north_nw",
    "青岛": "north_nw",
    "济南": "north_nw",
    "烟台": "north_nw",
    "淄博": "north_nw",
    "潍坊": "north_nw",
    "日照": "north_nw",
    "太原": "north_nw",
    "沈阳": "north_nw",
    "大连": "north_nw",
    "哈尔滨": "north_nw",
    "长春": "north_nw",
    "兰州": "north_nw",
    "银川": "north_nw",
    "乌鲁木齐": "north_nw",
    "呼和浩特": "north_nw",
}

CULTURE_BUREAU_PORTALS: list[dict[str, str]] = [
    {"name": "上海市文旅局审批公示", "region": "jzh", "url": "https://whlyj.sh.gov.cn/"},
    {"name": "北京市文旅局营业性演出公示", "region": "jjj", "url": "https://whlyj.beijing.gov.cn/"},
    {"name": "广东省文旅厅行政许可公示", "region": "gba", "url": "https://dct.gd.gov.cn/"},
    {"name": "浙江省文广旅厅审批公示", "region": "jzh", "url": "https://ct.zj.gov.cn/"},
    {"name": "江苏省文旅厅演出公示", "region": "jzh", "url": "https://wlt.jiangsu.gov.cn/"},
    {"name": "四川省文旅厅审批公示", "region": "cy", "url": "https://wlt.sc.gov.cn/"},
]

PRESET_ARTISTS: list[dict[str, Any]] = [
    # 华语乐队与歌手
    {"name": "万能青年旅店", "aliases": ["万青", "萬能青年旅店", "Omnipotent Youth Society"], "genre": "独立摇滚 / 器乐摇滚", "region_origin": "中国·石家庄", "category": "cn"},
    {"name": "落日飞车", "aliases": ["落日飛車", "Sunset Rollercoaster"], "genre": "浪漫合成器流行 / Indie", "region_origin": "台北", "category": "cn"},
    {"name": "草东没有派对", "aliases": ["草东", "草東沒有派對", "No Party For Cao Dong"], "genre": "独立摇滚", "region_origin": "台北", "category": "cn"},
    {"name": "五月天", "aliases": ["Mayday"], "genre": "华语流行摇滚", "region_origin": "台北", "category": "cn"},
    {"name": "周杰伦", "aliases": ["周杰倫", "Jay Chou", "周董"], "genre": "华语流行", "region_origin": "台北", "category": "cn"},
    {"name": "陶喆", "aliases": ["David Tao"], "genre": "R&B / 华语流行", "region_origin": "台北", "category": "cn"},
    {"name": "陈奕迅", "aliases": ["陳奕迅", "Eason Chan", "Eason"], "genre": "粤语/国语流行", "region_origin": "香港", "category": "cn"},
    {"name": "邓紫棋", "aliases": ["鄧紫棋", "G.E.M.", "GEM"], "genre": "华语流行", "region_origin": "香港", "category": "cn"},
    {"name": "林俊杰", "aliases": ["林俊傑", "JJ Lin", "JJ"], "genre": "华语流行", "region_origin": "新加坡", "category": "cn"},
    {"name": "孙燕姿", "aliases": ["孫燕姿", "Stefanie Sun"], "genre": "华语流行", "region_origin": "新加坡", "category": "cn"},
    {"name": "陈粒", "aliases": ["陳粒", "Chen Li"], "genre": "独立民谣 / 流行", "region_origin": "中国·贵阳", "category": "cn"},
    {"name": "新裤子", "aliases": ["新褲子", "New Pants", "新裤子乐队"], "genre": "新浪潮 / 合成器朋克", "region_origin": "中国·北京", "category": "cn"},
    {"name": "重塑雕像的权利", "aliases": ["重塑", "重塑雕像的權利", "Re-TROS"], "genre": "后朋克 / 电子摇滚", "region_origin": "中国·北京", "category": "cn"},
    {"name": "痛仰乐队", "aliases": ["痛仰", "痛仰樂隊", "Miserable Faith"], "genre": "摇滚", "region_origin": "中国·北京", "category": "cn"},
    {"name": "声音玩具", "aliases": ["聲音玩具", "Soundtoy"], "genre": "艺术摇滚", "region_origin": "中国·成都", "category": "cn"},
    {"name": "蛙池", "aliases": ["WaChi"], "genre": "独立摇滚", "region_origin": "中国·东莞", "category": "cn"},
    # 欧美乐队与歌手（原名检索）
    {"name": "Coldplay", "aliases": [], "genre": "英伦摇滚 / 流行摇滚", "region_origin": "英国·伦敦", "category": "intl_west"},
    {"name": "Imagine Dragons", "aliases": [], "genre": "流行摇滚 / 另类摇滚", "region_origin": "美国·拉斯维加斯", "category": "intl_west"},
    {"name": "OneRepublic", "aliases": ["One Republic"], "genre": "流行摇滚", "region_origin": "美国·科罗拉多", "category": "intl_west"},
    {"name": "Cigarettes After Sex", "aliases": [], "genre": "梦幻流行 / Dream Pop", "region_origin": "美国·得州", "category": "intl_west"},
    {"name": "Ed Sheeran", "aliases": [], "genre": "流行 / 民谣唱作", "region_origin": "英国", "category": "intl_west"},
    {"name": "Charlie Puth", "aliases": [], "genre": "欧美流行 / R&B", "region_origin": "美国", "category": "intl_west"},
    {"name": "Dua Lipa", "aliases": [], "genre": "舞曲流行 / Synth-Pop", "region_origin": "英国·伦敦", "category": "intl_west"},
    {"name": "Oasis", "aliases": [], "genre": "英伦摇滚 / Britpop", "region_origin": "英国·曼彻斯特", "category": "intl_west"},
    {"name": "Linkin Park", "aliases": [], "genre": "另类摇滚 / 新金属", "region_origin": "美国·加州", "category": "intl_west"},
    {"name": "Mariah Carey", "aliases": [], "genre": "R&B / 流行天后", "region_origin": "美国·纽约", "category": "intl_west"},
    {"name": "Bruno Mars", "aliases": [], "genre": "Funk / R&B / 流行", "region_origin": "美国·夏威夷", "category": "intl_west"},
    {"name": "Taylor Swift", "aliases": [], "genre": "欧美流行 / 唱作", "region_origin": "美国", "category": "intl_west"},
    {"name": "LANY", "aliases": [], "genre": "独立流行 / Synth-Pop", "region_origin": "美国·洛杉矶", "category": "intl_west"},
    {"name": "Radiohead", "aliases": ["Thom Yorke"], "genre": "另类摇滚 / 艺术摇滚", "region_origin": "英国·牛津", "category": "intl_west"},
    {"name": "Arctic Monkeys", "aliases": [], "genre": "独立摇滚 / 车库摇滚", "region_origin": "英国·谢菲尔德", "category": "intl_west"},
    {"name": "Muse", "aliases": [], "genre": "太空摇滚 / 前卫摇滚", "region_origin": "英国·德文郡", "category": "intl_west"},
    {"name": "Green Day", "aliases": [], "genre": "流行朋克 / 朋克摇滚", "region_origin": "美国·加州", "category": "intl_west"},
    {"name": "Maroon 5", "aliases": [], "genre": "流行摇滚 / Funk Pop", "region_origin": "美国·洛杉矶", "category": "intl_west"},
    {"name": "The 1975", "aliases": [], "genre": "独立流行 / Synth-Pop", "region_origin": "英国·曼彻斯特", "category": "intl_west"},
    {"name": "Suede", "aliases": [], "genre": "英伦摇滚 / Britpop", "region_origin": "英国·伦敦", "category": "intl_west"},
    {"name": "Tame Impala", "aliases": ["Kevin Parker"], "genre": "迷幻摇滚 / 迷幻流行", "region_origin": "澳大利亚·珀斯", "category": "intl_west"},
    {"name": "Billie Eilish", "aliases": [], "genre": "另类流行 / Electropop", "region_origin": "美国·洛杉矶", "category": "intl_west"},
    {"name": "Adele", "aliases": [], "genre": "灵魂乐 / 流行天后", "region_origin": "英国·伦敦", "category": "intl_west"},
    {"name": "The Weeknd", "aliases": [], "genre": "R&B / 合成器流行", "region_origin": "加拿大·多伦多", "category": "intl_west"},
    {"name": "Lana Del Rey", "aliases": [], "genre": "梦幻流行 / 巴洛克流行", "region_origin": "美国·纽约", "category": "intl_west"},
    {"name": "Lady Gaga", "aliases": [], "genre": "舞曲流行 / 流行摇滚", "region_origin": "美国·纽约", "category": "intl_west"},
    {"name": "Katy Perry", "aliases": [], "genre": "欧美流行", "region_origin": "美国·加州", "category": "intl_west"},
    {"name": "Sabrina Carpenter", "aliases": [], "genre": "欧美流行 / Dance-Pop", "region_origin": "美国·宾州", "category": "intl_west"},
    {"name": "Troye Sivan", "aliases": [], "genre": "电子流行 / Synth-Pop", "region_origin": "澳大利亚·珀斯", "category": "intl_west"},
    {"name": "Alan Walker", "aliases": [], "genre": "电子舞曲 / EDM", "region_origin": "挪威·卑尔根", "category": "intl_west"},
    {"name": "Martin Garrix", "aliases": [], "genre": "电子舞曲 / Progressive House", "region_origin": "荷兰·阿姆斯特丹", "category": "intl_west"},
    {"name": "HONNE", "aliases": [], "genre": "电子灵魂乐 / R&B", "region_origin": "英国·伦敦", "category": "intl_west"},
    {"name": "keshi", "aliases": [], "genre": "Lo-Fi R&B / 独立流行", "region_origin": "美国·休斯敦", "category": "intl_west"},
    # 日韩乐队与歌手（来华 / 港澳巡演热门）
    {"name": "YOASOBI", "aliases": ["ヨアソビ", "Ikura", "Ayase"], "genre": "J-Pop / 超现实流行", "region_origin": "日本·东京", "category": "intl_jpkr"},
    {"name": "Fujii Kaze", "aliases": ["藤井风", "藤井風"], "genre": "J-Pop / R&B / 爵士流行", "region_origin": "日本·冈山", "category": "intl_jpkr"},
    {"name": "Kenshi Yonezu", "aliases": ["米津玄师", "米津玄師"], "genre": "J-Pop / 摇滚唱作", "region_origin": "日本·德岛", "category": "intl_jpkr"},
    {"name": "RADWIMPS", "aliases": ["ラッドウィンプス"], "genre": "日本摇滚 / 动画电影配乐", "region_origin": "日本·横滨", "category": "intl_jpkr"},
    {"name": "Official HIGE DANdism", "aliases": ["Official髭男dism", "Official Hige Dandism"], "genre": "J-Pop / 钢琴流行摇滚", "region_origin": "日本·岛根", "category": "intl_jpkr"},
    {"name": "King Gnu", "aliases": ["キングヌー"], "genre": "日本混种摇滚 / Alternative", "region_origin": "日本·东京", "category": "intl_jpkr"},
    {"name": "Joe Hisaishi", "aliases": ["久石让", "久石譲"], "genre": "交响配乐 / 现代古典", "region_origin": "日本·长野", "category": "intl_jpkr"},
    {"name": "ONE OK ROCK", "aliases": ["OOR", "ワンオク"], "genre": "日本摇滚 / 另类摇滚", "region_origin": "日本·东京", "category": "intl_jpkr"},
    {"name": "Ado", "aliases": ["アド"], "genre": "J-Pop / 摇滚女声", "region_origin": "日本·东京", "category": "intl_jpkr"},
    {"name": "Hikaru Utada", "aliases": ["宇多田光", "宇多田ヒカル"], "genre": "J-Pop / R&B 天后", "region_origin": "日本·东京", "category": "intl_jpkr"},
    {"name": "Vaundy", "aliases": ["バウンディ"], "genre": "J-Pop / 独立摇滚", "region_origin": "日本·东京", "category": "intl_jpkr"},
    {"name": "back number", "aliases": ["バックナンバー"], "genre": "日系流行摇滚", "region_origin": "日本·群马", "category": "intl_jpkr"},
    {"name": "Yorushika", "aliases": ["ヨルシカ"], "genre": "日系摇滚 / 词曲企划", "region_origin": "日本·东京", "category": "intl_jpkr"},
    {"name": "ZUTOMAYO", "aliases": ["ずっと真夜中でいいのに。"], "genre": "J-Pop / 电子放克摇滚", "region_origin": "日本·东京", "category": "intl_jpkr"},
    {"name": "SEKAI NO OWARI", "aliases": ["セカオワ"], "genre": "日系梦幻流行摇滚", "region_origin": "日本·东京", "category": "intl_jpkr"},
    {"name": "G-DRAGON", "aliases": ["GD", "Kwon Ji-yong"], "genre": "K-Pop / Hip-Hop", "region_origin": "韩国·首尔", "category": "intl_jpkr"},
    {"name": "IU", "aliases": ["Lee Ji-eun", "이지은"], "genre": "K-Pop / 唱作歌手", "region_origin": "韩国·首尔", "category": "intl_jpkr"},
    {"name": "BLACKPINK", "aliases": ["블랙핑크"], "genre": "K-Pop 女子天团", "region_origin": "韩国·首尔", "category": "intl_jpkr"},
    {"name": "SEVENTEEN", "aliases": ["SVT", "세븐틴"], "genre": "K-Pop 男子团体", "region_origin": "韩国·首尔", "category": "intl_jpkr"},
    {"name": "aespa", "aliases": ["에스파"], "genre": "K-Pop / Hyperpop", "region_origin": "韩国·首尔", "category": "intl_jpkr"},
    {"name": "HYUKOH", "aliases": ["혁오"], "genre": "韩国独立摇滚 / Indie", "region_origin": "韩国·首尔", "category": "intl_jpkr"},
    {"name": "DAY6", "aliases": ["데이식스"], "genre": "韩国流行摇滚乐队", "region_origin": "韩国·首尔", "category": "intl_jpkr"},
    {"name": "LE SSERAFIM", "aliases": ["르세라핌"], "genre": "K-Pop 女子团体", "region_origin": "韩国·首尔", "category": "intl_jpkr"},
]

PLATFORM_PATTERNS: list[tuple[str, str]] = [
    (r"damai\.cn|大麦|大麥", "大麦"),
    (r"maoyan\.com|猫眼|貓眼", "猫眼"),
    (r"showstart\.com|秀动|秀動", "秀动"),
    (r"bilibili\.com|会员购|會員購|b站", "B站会员购"),
    (r"moretickets\.com|摩天轮|摩天輪", "摩天轮"),
    (r"纷玩岛|紛玩島|fenwandao", "纷玩岛"),
    (r"piaoxingqiu|票星球", "票星球"),
    (r"livenation\.cn|live\s*nation|理想国", "Live Nation"),
    (r"cotaiticketing|金光票务|金光票務", "金光票务"),
    (r"galaxymacau|银河票务|銀河票務", "银河票务"),
    (r"urbtix|城市售票网|城市售票網", "城市售票网"),
    (r"cityline", "Cityline"),
    (r"hkticketing|快达票|快達票", "快达票"),
    (r"kktix", "KKTIX"),
    (r"tixcraft|拓元", "拓元售票"),
    (r"ticketmaster", "Ticketmaster"),
]

VENUE_SPECIAL_RE = re.compile(
    r"(红磡香港体育馆|紅磡香港體育館|香港体育馆|香港體育館|红馆|紅館|启德主场馆|啟德主場館|启德体艺馆|啟德體藝館|"
    r"亚洲国际博览馆|亞洲國際博覽館|亚博馆|亞博館|中环海滨活动空间|中環海濱活動空間|"
    r"银河综艺馆|銀河綜藝館|威尼斯人综艺馆|威尼斯人綜藝館|金光综艺馆|金光綜藝館|伦敦人综艺馆|倫敦人綜藝館|新濠影汇综艺馆|新濠影匯綜藝館|"
    r"台北小巨蛋|臺北小巨蛋|台北大巨蛋|臺北大巨蛋|高雄巨蛋|高雄世运主场馆|高雄世運主場館)"
)

VENUE_SUFFIX_RE = re.compile(
    r"([\u4e00-\u9fa5A-Za-z0-9·•\-—（）()]{2,30}?"
    r"(?:体育场|體育場|体育馆|體育館|文化中心|演艺中心|演藝中心|大剧院|大劇院|艺术中心|藝術中心|"
    r"音乐厅|音樂廳|展览中心|展覽中心|博览中心|博覽中心|综艺馆|綜藝館|主场馆|主場館|小巨蛋|大巨蛋|"
    r"Livehouse|LIVEHOUSE|LiveHouse|SPACE|Space|空间|空間|剧场|劇場|俱乐部|俱樂部|中心|公园|公園|草坪|营地|營地))"
)

CITY_ALIAS_MAP: dict[str, str] = {
    "澳門": "澳门",
    "臺北": "台北",
    "臺中": "台中",
    "臺南": "台南",
    "紅磡": "香港",
    "红磡": "香港",
    "啟德": "香港",
    "启德": "香港",
}

CITY_SORTED = sorted(list(CITY_TO_REGION.keys()) + list(CITY_ALIAS_MAP.keys()), key=len, reverse=True)
CITY_ALTERNATION = "|".join(re.escape(c) for c in CITY_SORTED)
CITY_RE = re.compile(rf"(?:[\[【(（]\s*)?({CITY_ALTERNATION})(?:市|縣|县|站)?(?:\s*[\]】)）])?")


def normalize_city_name(city: str) -> str:
    clean = (city or "").strip().rstrip("市县縣站")
    return CITY_ALIAS_MAP.get(clean, clean)


def infer_region(city: str) -> str:
    clean = normalize_city_name(city)
    return CITY_TO_REGION.get(clean, "other")


def detect_platform(text: str, url: str = "") -> str:
    combined = f"{url}\n{text}"
    for pattern, label in PLATFORM_PATTERNS:
        if re.search(pattern, combined, flags=re.IGNORECASE):
            return label
    return "大麦"


def extract_https_url(text: str) -> str:
    match = re.search(r"https://[^\s<>\"'）)】\]]+", text)
    if not match:
        return ""
    return match.group(0).rstrip(".,;，。！？!?)")


def _parse_local_dt(dt_str: str) -> datetime.datetime | None:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            naive = datetime.datetime.strptime(dt_str.strip(), fmt)
            if fmt == "%Y-%m-%d":
                naive = naive.replace(hour=19, minute=30)
            return naive.replace(tzinfo=SHANGHAI_TZ)
        except ValueError:
            continue
    return None


def _normalize_year(year_str: str | None, month: int, day: int, now: datetime.datetime) -> int:
    if year_str:
        y = int(year_str)
        return y + 2000 if y < 100 else y
    candidate_year = now.year
    try:
        candidate = datetime.date(candidate_year, month, day)
        if candidate < (now.date() - datetime.timedelta(days=14)):
            return candidate_year + 1
    except ValueError:
        pass
    return candidate_year


def _parse_datetime_from_segment(
    segment: str, now: datetime.datetime, default_hour: int = 19, default_minute: int = 30
) -> str | None:
    date_match = re.search(
        r"(?:(20\d{2})\s*[年/.\-]\s*)?(\d{1,2})\s*[月/.\-]\s*(\d{1,2})\s*日?",
        segment,
    )
    if not date_match:
        return None
    month = int(date_match.group(2))
    day = int(date_match.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    year = _normalize_year(date_match.group(1), month, day, now)

    after_date = segment[date_match.end() :]
    time_match = re.search(r"(\d{1,2})\s*[:：]\s*(\d{2})", after_date)
    if not time_match:
        time_match = re.search(r"(\d{1,2})\s*[:：]\s*(\d{2})", segment)

    hour = int(time_match.group(1)) if time_match else default_hour
    minute = int(time_match.group(2)) if time_match else default_minute
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        hour, minute = default_hour, default_minute

    try:
        dt = datetime.datetime(year, month, day, hour, minute)
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _extract_multi_night_datetimes(
    segment: str, now: datetime.datetime, default_hour: int = 19, default_minute: int = 30
) -> list[str]:
    """Extracts one or more consecutive/enumerated show nights from a single line (e.g. 12月19日-20日 19:30)."""
    base_dt_str = _parse_datetime_from_segment(segment, now, default_hour=default_hour, default_minute=default_minute)
    if not base_dt_str:
        return []

    # Check for consecutive day range in the same month: 2026年12月19日-20日 or 12.19-12.21 or 12月19日/20日/21日
    base_dt = _parse_local_dt(base_dt_str)
    if not base_dt:
        return [base_dt_str]

    hr, mn = base_dt.hour, base_dt.minute
    yr, mo = base_dt.year, base_dt.month

    range_m = re.search(
        r"(?:20\d{2}\s*[年/.\-]\s*)?(\d{1,2})\s*[月/.\-]\s*(\d{1,2})\s*日?\s*(?:[-~—至])\s*(?:\1\s*[月/.\-]\s*)?(\d{1,2})\s*日?",
        segment,
    )
    if range_m:
        m_num = int(range_m.group(1))
        d_start = int(range_m.group(2))
        d_end = int(range_m.group(3))
        if m_num == mo and d_start < d_end and (d_end - d_start) <= 4:
            out = []
            for d in range(d_start, d_end + 1):
                try:
                    out.append(datetime.datetime(yr, mo, d, hr, mn).strftime("%Y-%m-%d %H:%M"))
                except ValueError:
                    pass
            if len(out) >= 2:
                return out

    # Check slash / 顿号 enumerated days: 12月19日/20日/21日 or 12月19、20日
    enum_m = re.search(
        r"(?:20\d{2}\s*[年/.\-]\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日?(?:\s*[/、]\s*(?:\1\s*月\s*)?\d{1,2}\s*日?)+",
        segment,
    )
    if enum_m and int(enum_m.group(1)) == mo:
        day_tokens = re.findall(r"(?<!\d)(\d{1,2})\s*日?", enum_m.group(0)[enum_m.group(0).find("月") + 1 :])
        out_enum = []
        for dt_tok in day_tokens[:5]:
            d_val = int(dt_tok)
            if 1 <= d_val <= 31:
                try:
                    cand_s = datetime.datetime(yr, mo, d_val, hr, mn).strftime("%Y-%m-%d %H:%M")
                    if cand_s not in out_enum:
                        out_enum.append(cand_s)
                except ValueError:
                    pass
        if len(out_enum) >= 2:
            return out_enum

    return [base_dt_str]


def _extract_price(text: str) -> str:
    currency_match = re.search(
        r"((?:HK\$|MOP\s*\$?|NT\$)\s*\d{3,5}(?:\s*[/\-~—、]\s*(?:HK\$|MOP\s*\$?|NT\$)?\s*\d{3,5})*)",
        text,
        flags=re.IGNORECASE,
    )
    if currency_match:
        return re.sub(r"\s+", "", currency_match.group(1))

    explicit = re.search(
        r"(?:票价|票價|价格|價格|预售|預售|单价|單價)\s*[:：]?\s*([¥￥]?\s*\d{2,4}(?:\s*[-/~—至/、]\s*[¥￥]?\s*\d{2,4})*(?:元|起)?)",
        text,
    )
    if explicit:
        val = explicit.group(1).strip()
        return val if val.startswith(("¥", "￥")) else f"¥{val}"

    yuan_symbol = re.search(r"[¥￥]\s*\d{2,4}(?:\s*[-/~—]\s*\d{2,4})?(?:起)?", text)
    if yuan_symbol:
        return yuan_symbol.group(0).replace("￥", "¥").replace(" ", "")

    yuan_word = re.search(r"\b(\d{2,4}(?:\s*/\s*\d{2,4}){1,6})\s*(?:元|港币|港幣)", text)
    if yuan_word:
        return f"¥{yuan_word.group(1).replace(' ', '')}"
    return ""


def _extract_ticket_rounds(
    lines: list[str], now: datetime.datetime, platform: str, ticket_url: str
) -> list[dict[str, str]]:
    sale_keywords = [
        ("优先购", r"优先购|優先購|粉丝先享|粉絲先享|先享购|会员优先|會員優先|信用卡優先"),
        ("二开", r"二开|二開|二次开票|二次開票|二轮开票|加场开票|加場開售"),
        ("回流蹲守", r"回流票|退票重开|退票重開|三开|三開"),
        (
            "一开",
            r"预售开启|預售開啟|正式预售|开票时间|開票時間|抢票时间|搶票時間|开售时间|開售時間|"
            r"公开发售|公開發售|全面开售|全面開售|正式开票|正式開票|预售时间|开票|開票|抢票|搶票|开售|開售",
        ),
    ]
    rounds: list[dict[str, str]] = []
    seen_times: set[str] = set()

    for idx, line in enumerate(lines):
        if re.search(r"退票|手续费|手續費|无条件退|無條件退|停止退", line):
            continue
        matched_label = None
        for label, kw_re in sale_keywords:
            if re.search(kw_re, line):
                matched_label = label
                break
        if not matched_label:
            continue

        dt_str = _parse_datetime_from_segment(line, now, default_hour=12, default_minute=18)
        if not dt_str and idx + 1 < len(lines):
            dt_str = _parse_datetime_from_segment(lines[idx + 1], now, default_hour=12, default_minute=18)
        if dt_str and dt_str not in seen_times:
            seen_times.add(dt_str)
            line_platform = (
                detect_platform(line, "")
                if any(
                    p in line
                    for p in (
                        "大麦",
                        "大麥",
                        "猫眼",
                        "貓眼",
                        "秀动",
                        "秀動",
                        "纷玩岛",
                        "紛玩島",
                        "B站",
                        "会员购",
                        "城市售票",
                        "Cityline",
                        "cityline",
                        "快达票",
                        "快達票",
                        "KKTIX",
                        "拓元",
                    )
                )
                else platform
            )
            rounds.append(
                {
                    "round_label": matched_label,
                    "sale_time": dt_str,
                    "platform": line_platform,
                    "booking_url": ticket_url,
                }
            )
    return rounds


def build_standard_damai_refund_tiers(first_sale_time: str, show_time: str) -> list[dict[str, Any]]:
    """Generates typical Mainland China tiered refund & returned-ticket drop timestamps."""
    tiers: list[dict[str, Any]] = []
    sale_dt = _parse_local_dt(first_sale_time) if first_sale_time else None
    show_dt = _parse_local_dt(show_time) if show_time else None

    if sale_dt:
        free_end = sale_dt + datetime.timedelta(hours=48)
        tiers.append(
            {
                "tier_label": "无条件退截止（首波回流）",
                "cutoff_time": free_end.strftime("%Y-%m-%d %H:%M"),
                "fee_percent": 0,
                "expect_return_drop": True,
            }
        )
    if show_dt:
        t20 = (show_dt - datetime.timedelta(days=7)).replace(hour=12, minute=0)
        if not sale_dt or t20 > sale_dt + datetime.timedelta(hours=50):
            tiers.append(
                {
                    "tier_label": "20%手续费截止（二波回流）",
                    "cutoff_time": t20.strftime("%Y-%m-%d %H:%M"),
                    "fee_percent": 20,
                    "expect_return_drop": True,
                }
            )
        stop_dt = (show_dt - datetime.timedelta(days=2)).replace(hour=12, minute=0)
        tiers.append(
            {
                "tier_label": "停止退票截止",
                "cutoff_time": stop_dt.strftime("%Y-%m-%d %H:%M"),
                "fee_percent": 100,
                "expect_return_drop": False,
            }
        )
    return tiers


def _extract_refund_tiers(
    lines: list[str],
    now: datetime.datetime,
    ticket_rounds: list[dict[str, str]],
) -> list[dict[str, Any]]:
    tiers: list[dict[str, Any]] = []
    seen_cutoffs: set[str] = set()

    for line in lines:
        if not re.search(r"退票|无条件退|無條件退|免手续费|免手續費|手续费|手續費|停止退", line):
            continue

        # Handle relative rule like "开票后48小时内无条件退票"
        rel_hours = re.search(
            r"(?:开票|開票|预售|預售)(?:开启|開啟)?[后後]?\s*(\d{1,2})\s*小[时時][内內]?(?:无条件|無條件|免费|免費|免手续费|免手續費)退",
            line,
        )
        if rel_hours and ticket_rounds:
            base_dt = _parse_local_dt(ticket_rounds[0]["sale_time"])
            if base_dt:
                cutoff_str = (base_dt + datetime.timedelta(hours=int(rel_hours.group(1)))).strftime("%Y-%m-%d %H:%M")
                if cutoff_str not in seen_cutoffs:
                    seen_cutoffs.add(cutoff_str)
                    tiers.append(
                        {
                            "tier_label": "无条件退截止（首波回流）",
                            "cutoff_time": cutoff_str,
                            "fee_percent": 0,
                            "expect_return_drop": True,
                        }
                    )
                continue

        dt_str = _parse_datetime_from_segment(line, now, default_hour=12, default_minute=0)
        if not dt_str or dt_str in seen_cutoffs:
            continue
        seen_cutoffs.add(dt_str)

        if re.search(r"停止退票|不再接受退票|不可退", line):
            tiers.append(
                {
                    "tier_label": "停止退票截止",
                    "cutoff_time": dt_str,
                    "fee_percent": 100,
                    "expect_return_drop": False,
                }
            )
        elif re.search(r"无条件退|無條件退|免手续费|免手續費|(?<!\d)0%|免费退|免費退", line):
            tiers.append(
                {
                    "tier_label": "无条件退截止（首波回流）",
                    "cutoff_time": dt_str,
                    "fee_percent": 0,
                    "expect_return_drop": True,
                }
            )
        else:
            fee_m = re.search(r"(\d{1,2})\s*%", line)
            fee_pct = int(fee_m.group(1)) if fee_m else 20
            tiers.append(
                {
                    "tier_label": f"{fee_pct}%手续费截止（回流蹲守）",
                    "cutoff_time": dt_str,
                    "fee_percent": fee_pct,
                    "expect_return_drop": True,
                }
            )

    return tiers


def _detect_culture_bureau_approval(text: str) -> tuple[bool, str, str]:
    """Detects Ministry/Bureau of Culture & Tourism administrative approval announcements."""
    is_approval = bool(
        re.search(
            r"文旅许|文广旅|文化和旅游厅|文化和旅游局|营业性演出准予许可|行政许可决定|批复文号|准予举办",
            text,
        )
    )
    if not is_approval:
        return False, "", ""

    doc_m = re.search(
        r"([\u4e00-\u9fa5]{1,6}(?:文旅|文广旅)[\u4e00-\u9fa5]{0,3}[〔\[（(]20\d{2}[〕\]）)]\s*(?:[\u4e00-\u9fa5]{0,4})?\d+\s*号)",
        text,
    )
    if not doc_m:
        doc_m = re.search(r"(?:批文号|许可文号|文号|编号)\s*[:：]?\s*([^\n，,。；;]{4,30})", text)
    doc_no = doc_m.group(1).strip() if doc_m else "已公示过审"

    src_m = re.search(
        r"([\u4e00-\u9fa5]{2,10}(?:省|市|自治区)?文化和旅游(?:厅|局)|[\u4e00-\u9fa5]{2,10}文化广电和旅游(?:厅|局))",
        text,
    )
    source = src_m.group(1).strip() if src_m else "省/市文旅局官网公示"
    return True, doc_no, source


def _extract_festival_info_and_lineup(
    text: str, lines: list[str], headline: str, now: datetime.datetime
) -> tuple[str, str, list[dict[str, str]]]:
    """Detects whether announcement is a multi-band music festival and extracts stage/time slots."""
    fest_m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·•]{2,22}(?:音乐节|音乐嘉年华))", headline + "\n" + text)
    if not fest_m:
        return "concert", "", []

    fest_name = fest_m.group(1).strip()
    lineup: list[dict[str, str]] = []
    current_day = ""

    for ln in lines:
        day_m = re.search(r"(?:(20\d{2})\s*[年/.\-])?(\d{1,2})\s*[月/.\-](\d{1,2})\s*日?", ln)
        slot_m = re.search(r"(\d{1,2}:\d{2})\s*[-—~至]\s*(\d{1,2}:\d{2})", ln)
        if day_m and not slot_m and len(ln) <= 28:
            mo, dy = int(day_m.group(2)), int(day_m.group(3))
            yr = _normalize_year(day_m.group(1), mo, dy, now)
            try:
                current_day = datetime.date(yr, mo, dy).strftime("%Y-%m-%d")
            except ValueError:
                pass
            continue

        if slot_m:
            if day_m:
                mo, dy = int(day_m.group(2)), int(day_m.group(3))
                yr = _normalize_year(day_m.group(1), mo, dy, now)
                try:
                    slot_day = datetime.date(yr, mo, dy).strftime("%Y-%m-%d")
                except ValueError:
                    slot_day = current_day
            else:
                slot_day = current_day

            stage_m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{1,10}舞台)", ln)
            stage = stage_m.group(1) if stage_m else "主舞台"

            # Remove date, time range, and stage to isolate artist name
            cleaned = ln
            if day_m:
                cleaned = cleaned.replace(day_m.group(0), " ")
            cleaned = cleaned.replace(slot_m.group(0), " ")
            if stage_m:
                cleaned = cleaned.replace(stage_m.group(0), " ")
            artist_part = re.sub(r"[|｜·•\-—:：\[\]【】]", " ", cleaned).strip()
            if artist_part:
                lineup.append(
                    {
                        "artist": artist_part[:32],
                        "stage": stage,
                        "day_date": slot_day,
                        "set_start": slot_m.group(1),
                        "set_end": slot_m.group(2),
                    }
                )

    return "festival", fest_name, lineup


def _extract_artist_name(text: str, lines: list[str], known_artists: list[dict[str, Any]]) -> str:
    lowered = text.lower()
    matched_names: list[str] = []
    for artist in known_artists:
        candidates = [artist["name"]] + list(artist.get("aliases") or [])
        for cand in candidates:
            c = cand.strip()
            if c and c.lower() in lowered:
                if artist["name"] not in matched_names:
                    matched_names.append(artist["name"])
                break

    if not matched_names:
        for preset in PRESET_ARTISTS:
            for cand in [preset["name"]] + preset["aliases"]:
                if cand.lower() in lowered:
                    if preset["name"] not in matched_names:
                        matched_names.append(preset["name"])
                    break

    if matched_names:
        return " / ".join(matched_names[:4])

    explicit = re.search(
        r"(?:艺人|藝人|演出艺人|演出藝人|嘉宾|嘉賓|乐队|樂隊|歌手|主演|申请演出演员|申請演出演員)\s*[:：]\s*([^\n|｜/]{2,28})",
        text,
    )
    if explicit:
        return explicit.group(1).strip()

    for line in lines[:4]:
        tour_prefix = re.match(
            r"^(?:[\[【《「])?([\u4e00-\u9fa5A-Za-z0-9·\s]{2,16}?)(?:[\]】》」])?\s*(?:20\d{2})?\s*"
            r"(?:「[^」]+」|《[^》]+》)?\s*(?:世界)?(?:巡回演唱会|巡迴演唱會|演唱会|演唱會|巡演|专场|專場|音乐会|音樂會)",
            line,
        )
        if tour_prefix:
            cand = tour_prefix.group(1).strip()
            if cand not in ("官宣", "重磅", "演出", "正式", "最新", "关于准予举办", "關於准予舉辦"):
                return cand

        approval_actor = re.search(
            r"(?:举办|舉辦)[《「]?([\u4e00-\u9fa5A-Za-z0-9·]{2,14}?)(?:20\d{2})?(?:巡回演唱会|巡迴演唱會|演唱会|演唱會|个人演唱会|個人演唱會)",
            line,
        )
        if approval_actor:
            return approval_actor.group(1).strip()

    return ""


def _extract_venue(segment: str, city: str) -> str:
    explicit = re.search(r"(?:场馆|場館|地点|地點|场地|場地|地址|位置|演出场所|演出場所)\s*[:：]\s*([^\n|｜]{2,36})", segment)
    if explicit:
        v = explicit.group(1).strip()
        v = re.sub(rf"^[\[【(（]{re.escape(city)}[\]】)）]\s*", "", v) if city else v
        return v.strip()

    bracket_after_city = (
        re.search(rf"[\[【]{re.escape(city)}[\]】]\s*([^\n|｜,，]{2,30})", segment) if city else None
    )
    if bracket_after_city:
        return bracket_after_city.group(1).strip()

    special_match = VENUE_SPECIAL_RE.search(segment)
    if special_match:
        return special_match.group(1).strip()

    v_match = VENUE_SUFFIX_RE.search(segment)
    if v_match:
        return v_match.group(1).strip()
    return ""


def parse_concert_announcement(
    raw_text: str,
    known_artists: list[dict[str, Any]] | None = None,
    now: datetime.datetime | None = None,
) -> dict[str, Any]:
    """Parses Weibo/Damai/ShowStart, Festival lineups, or Culture Bureau approval notices into concert items."""
    clean_text = (raw_text or "").strip()
    if not clean_text:
        return {"items": [], "summary": "请输入或粘贴官宣/审批/音乐节文案"}

    ref_now = now or datetime.datetime.now(SHANGHAI_TZ)
    lines = [ln.strip() for ln in clean_text.splitlines() if ln.strip()]
    known = known_artists or []

    ticket_url = extract_https_url(clean_text)
    platform = detect_platform(clean_text, ticket_url)
    is_approval, approval_doc_no, approval_source = _detect_culture_bureau_approval(clean_text)
    artist_name = _extract_artist_name(clean_text, lines, known)
    price_text = _extract_price(clean_text)
    ticket_rounds = _extract_ticket_rounds(lines, ref_now, platform, ticket_url)
    refund_tiers = _extract_refund_tiers(lines, ref_now, ticket_rounds)

    headline = ""
    for ln in lines:
        if re.match(
            r"^(?:时间|時間|演出时间|演出時間|日期|地点|地點|场馆|場館|票价|票價|价格|價格|开票|開票|公开发售|公開發售|抢票|搶票|退票|艺人|藝人|批文|https://)",
            ln,
        ):
            continue
        headline = re.sub(r"#([^#]+)#", r"\1", ln).strip()
        break
    if not headline:
        headline = f"{artist_name or '现场演出'} 演唱会"

    event_kind, festival_name, lineup = _extract_festival_info_and_lineup(clean_text, lines, headline, ref_now)
    if event_kind == "festival" and not artist_name and lineup:
        artist_name = " / ".join(dict.fromkeys(s["artist"] for s in lineup[:4]))

    default_hour, default_min = (
        (13, 30)
        if event_kind == "festival"
        else ((20, 0) if ("livehouse" in clean_text.lower() or platform == "秀动") else (19, 30))
    )

    sale_or_refund_lines = {
        ln
        for ln in lines
        if re.search(
            r"优先购|優先購|开票|開票|公开发售|公開發售|抢票|搶票|开售|開售|预售开启|預售開啟|二开|二開|粉丝先享|粉絲先享|退票|无条件退|無條件退|手续费|手續費",
            ln,
        )
    }

    default_status = (
        "approved_pending"
        if is_approval and not ticket_rounds
        else ("upcoming_drop" if ticket_rounds else "announced")
    )

    # Multi-stop tour detection (skip when festival stage timetable has multiple lines in same city)
    stop_items: list[dict[str, Any]] = []
    if event_kind != "festival":
        for ln in lines:
            if ln in sale_or_refund_lines:
                continue
            city_match = CITY_RE.search(ln)
            dt_list = _extract_multi_night_datetimes(
                ln, ref_now, default_hour=default_hour, default_minute=default_min
            )
            if city_match and dt_list:
                raw_city = city_match.group(1)
                city = normalize_city_name(raw_city)
                venue = _extract_venue(ln, raw_city) or _extract_venue(ln, city)
                base_stop_title = headline if city in headline else f"{headline}（{city}站）"
                for dt_str in dt_list:
                    stop_title = (
                        f"{base_stop_title} · {dt_str[:10]}场" if len(dt_list) > 1 else base_stop_title
                    )
                    stop_items.append(
                        {
                            "artist_name": artist_name,
                            "title": stop_title[:120],
                            "city": city,
                            "region": infer_region(city),
                            "venue": venue,
                            "show_time": dt_str,
                            "price_text": price_text,
                            "platform": "文旅局公示" if is_approval and not ticket_url else platform,
                            "ticket_url": ticket_url,
                            "status": default_status,
                            "event_kind": "concert",
                            "festival_name": "",
                            "lineup": [],
                            "approval_doc_no": approval_doc_no,
                            "approval_source": approval_source,
                            "source_type": "smart_paste",
                            "ticket_rounds": [dict(r) for r in ticket_rounds],
                            "refund_tiers": [dict(rf) for rf in refund_tiers],
                        }
                    )

    if len(stop_items) >= 2:
        return {
            "items": stop_items,
            "multi_stop": True,
            "summary": f"识别到多场次巡演排期（共 {len(stop_items)} 场，{len(refund_tiers)} 条退票/回流节点）",
        }

    non_sale_text = "\n".join(ln for ln in lines if ln not in sale_or_refund_lines)
    city_match = CITY_RE.search(non_sale_text) or CITY_RE.search(clean_text)
    raw_city_single = city_match.group(1) if city_match else "上海"
    city = normalize_city_name(raw_city_single)
    if not city and VENUE_SPECIAL_RE.search(clean_text):
        sp_v = VENUE_SPECIAL_RE.search(clean_text).group(1)
        if any(k in sp_v for k in ("红馆", "紅館", "启德", "啟德", "亚博", "亞博", "中环", "中環")):
            city = "香港"
        elif any(k in sp_v for k in ("银河", "銀河", "威尼斯人", "金光", "伦敦人", "倫敦人", "新濠")):
            city = "澳门"
        elif "小巨蛋" in sp_v or "大巨蛋" in sp_v:
            city = "台北"

    show_dts: list[str] = []
    for ln in lines:
        if ln in sale_or_refund_lines:
            continue
        if re.search(r"演出时间|演出時間|演出日期|时间|時間|日期|举办日期|舉辦日期", ln):
            show_dts = (
                [_parse_datetime_from_segment(ln, ref_now, default_hour=default_hour, default_minute=default_min)]
                if event_kind == "festival"
                else _extract_multi_night_datetimes(ln, ref_now, default_hour=default_hour, default_minute=default_min)
            )
            show_dts = [d for d in show_dts if d]
            if show_dts:
                break
    if not show_dts:
        for ln in lines:
            if ln in sale_or_refund_lines:
                continue
            show_dts = (
                [_parse_datetime_from_segment(ln, ref_now, default_hour=default_hour, default_minute=default_min)]
                if event_kind == "festival"
                else _extract_multi_night_datetimes(ln, ref_now, default_hour=default_hour, default_minute=default_min)
            )
            show_dts = [d for d in show_dts if d]
            if show_dts:
                break
    if not show_dts:
        fallback_dt = ref_now + datetime.timedelta(days=30)
        show_dts = [
            fallback_dt.replace(hour=default_hour, minute=default_min, second=0, microsecond=0).strftime(
                "%Y-%m-%d %H:%M"
            )
        ]

    venue = (
        _extract_venue(non_sale_text, raw_city_single)
        or _extract_venue(non_sale_text, city)
        or _extract_venue(clean_text, city)
    )

    if len(show_dts) >= 2 and event_kind != "festival":
        night_items = []
        for idx_n, s_dt in enumerate(show_dts, start=1):
            night_items.append(
                {
                    "artist_name": artist_name,
                    "title": f"{headline}（第{idx_n}场 · {s_dt[:10]}）"[:120],
                    "city": city,
                    "region": infer_region(city),
                    "venue": venue,
                    "show_time": s_dt,
                    "price_text": price_text,
                    "platform": "文旅局公示" if is_approval and not ticket_url else platform,
                    "ticket_url": ticket_url,
                    "status": default_status,
                    "event_kind": "concert",
                    "festival_name": "",
                    "lineup": [],
                    "approval_doc_no": approval_doc_no,
                    "approval_source": approval_source,
                    "source_type": "smart_paste",
                    "ticket_rounds": [dict(r) for r in ticket_rounds],
                    "refund_tiers": [dict(rf) for rf in refund_tiers],
                }
            )
        return {
            "items": night_items,
            "multi_stop": True,
            "summary": f"已识别同城连开 {len(night_items)} 场：{artist_name or '待确认艺人'} · {city}站",
        }

    single_item = {
        "artist_name": artist_name or festival_name,
        "title": headline[:120],
        "city": city,
        "region": infer_region(city),
        "venue": venue,
        "show_time": show_dts[0],
        "price_text": price_text,
        "platform": "文旅局公示" if is_approval and not ticket_url else platform,
        "ticket_url": ticket_url,
        "status": default_status,
        "event_kind": event_kind,
        "festival_name": festival_name,
        "lineup": lineup,
        "approval_doc_no": approval_doc_no,
        "approval_source": approval_source,
        "source_type": "smart_paste",
        "ticket_rounds": ticket_rounds,
        "refund_tiers": refund_tiers,
    }

    mode_tag = "文旅审批过审" if is_approval else ("音乐节拼盘" if event_kind == "festival" else "专场演出")
    return {
        "items": [single_item],
        "multi_stop": False,
        "summary": f"已识别 [{mode_tag}]：{single_item['artist_name'] or '待确认艺人'} · {city}站",
    }


NON_12306_CITIES = {"台北", "高雄", "台中", "台南"}


def compute_12306_plan(home_city: str, concert: dict[str, Any]) -> dict[str, Any]:
    """Calculates cross-city 12306 15-day pre-sale dates and regional high-speed rail corridor hints."""
    clean_home = normalize_city_name(home_city)
    target_city = normalize_city_name(concert.get("city") or "")
    if (
        not clean_home
        or not target_city
        or target_city in ("待定", clean_home)
        or target_city in NON_12306_CITIES
        or clean_home in NON_12306_CITIES
    ):
        return {"is_cross_city": False}

    show_dt = _parse_local_dt(concert.get("show_time", ""))
    if not show_dt:
        return {"is_cross_city": False}

    # Afternoon festivals (< 15:30) usually require arriving the day before; evening shows allow same-day morning train
    outbound_travel_date = show_dt.date() - datetime.timedelta(days=1) if show_dt.hour < 15 else show_dt.date()
    return_travel_date = show_dt.date() + datetime.timedelta(days=1)

    # 12306 opens tickets 15 days inclusive (travel_date - 14 days)
    outbound_sale_date = outbound_travel_date - datetime.timedelta(days=14)
    return_sale_date = return_travel_date - datetime.timedelta(days=14)

    home_reg = infer_region(clean_home)
    dest_reg = infer_region(target_city)
    if target_city == "澳门":
        corridor = f"{clean_home} → 珠海站（拱北/横琴口岸通关赴澳门）高铁联动"
    elif target_city == "香港":
        corridor = f"{clean_home} → 香港西九龙站 跨境高铁联动"
    elif home_reg == dest_reg and home_reg in ("jzh", "gba", "jjj", "cy"):
        corridor = f"{REGION_LABELS.get(home_reg, '同区域')}城际高铁圈（约 0.5–2h）"
    else:
        corridor = f"{clean_home} → {target_city} 跨区出行（建议高铁/机票同步关注）"

    return {
        "is_cross_city": True,
        "home_city": clean_home,
        "target_city": target_city,
        "corridor": corridor,
        "outbound_travel_date": outbound_travel_date.strftime("%Y-%m-%d"),
        "outbound_12306_sale_time": f"{outbound_sale_date.strftime('%Y-%m-%d')} 08:00",
        "return_travel_date": return_travel_date.strftime("%Y-%m-%d"),
        "return_12306_sale_time": f"{return_sale_date.strftime('%Y-%m-%d')} 08:00",
        "station_batch_tip": "12306 按出发站 08:00–18:00 分批放票，建议提前在 App 开启「起售提醒」",
        "rail_booked": bool(concert.get("rail_booked")),
    }


def _hhmm_to_min(hhmm: str) -> int | None:
    m = re.match(r"^(\d{1,2}):(\d{2})$", (hhmm or "").strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def analyze_festival_groups(
    concerts: list[dict[str, Any]],
    followed_artists: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Groups festival concerts, calculates single-day followed-band overlap, and detects set-time clashes."""
    followed_terms: dict[str, list[str]] = {}
    for a in followed_artists:
        followed_terms[a["name"]] = [a["name"].lower()] + [x.lower() for x in (a.get("aliases") or []) if x]

    groups: dict[str, dict[str, Any]] = {}
    for c in concerts:
        title_str = c.get("title", "")
        is_fest = c.get("event_kind") == "festival" or (
            bool(re.search(r"音乐节|音乐嘉年华", title_str)) and "演唱会" not in title_str
        )
        if not is_fest:
            continue
        fest_title = (c.get("festival_name") or c.get("title") or "").strip()
        key = f"{c.get('city', '')}::{fest_title}"
        grp = groups.setdefault(
            key,
            {
                "festival_name": fest_title,
                "city": c.get("city", ""),
                "region": c.get("region", "other"),
                "venue": c.get("venue", ""),
                "show_time": c.get("show_time", ""),
                "price_text": c.get("price_text", ""),
                "platform": c.get("platform", ""),
                "ticket_url": c.get("ticket_url", ""),
                "concert_ids": [],
                "matched_artists": [],
                "slots": [],
            },
        )
        grp["concert_ids"].append(c["id"])
        for part in re.split(r"[/、,，]", c.get("artist_name") or ""):
            p = part.strip()
            if p and p not in grp["matched_artists"]:
                grp["matched_artists"].append(p)

        for slot in c.get("lineup") or []:
            if isinstance(slot, dict) and slot.get("artist"):
                if slot not in grp["slots"]:
                    grp["slots"].append(slot)

    results: list[dict[str, Any]] = []
    for grp in groups.values():
        # Score which single-day date has the highest overlap with followed artists
        day_artists: dict[str, list[str]] = collections.defaultdict(list)
        slots_by_day: dict[str, list[dict[str, str]]] = collections.defaultdict(list)

        for sl in grp["slots"]:
            day = sl.get("day_date") or grp["show_time"][:10]
            slots_by_day[day].append(sl)
            art_low = sl["artist"].lower()
            is_fav = any(any(t in art_low for t in terms) for terms in followed_terms.values()) or (
                sl["artist"] in grp["matched_artists"]
            )
            if is_fav and sl["artist"] not in day_artists[day]:
                day_artists[day].append(sl["artist"])

        best_day = ""
        best_count = 0
        for d, arts in sorted(day_artists.items()):
            if len(arts) > best_count:
                best_day = d
                best_count = len(arts)

        # Detect overlapping set times (clashes) on the same day, including post-midnight sets (e.g. 23:30-00:15)
        clashes: list[str] = []
        for day, day_slots in slots_by_day.items():
            for i in range(len(day_slots)):
                s1 = day_slots[i]
                st1, en1 = _hhmm_to_min(s1.get("set_start", "")), _hhmm_to_min(s1.get("set_end", ""))
                if st1 is None or en1 is None:
                    continue
                if en1 <= st1:
                    en1 += 24 * 60
                for j in range(i + 1, len(day_slots)):
                    s2 = day_slots[j]
                    st2, en2 = _hhmm_to_min(s2.get("set_start", "")), _hhmm_to_min(s2.get("set_end", ""))
                    if st2 is None or en2 is None:
                        continue
                    if en2 <= st2:
                        en2 += 24 * 60
                    overlap = min(en1, en2) - max(st1, st2)
                    if overlap > 0:
                        clashes.append(
                            f"{day} 撞场：{s1['artist']}（{s1.get('stage', '')} {s1['set_start']}-{s1['set_end']}） vs "
                            f"{s2['artist']}（{s2.get('stage', '')} {s2['set_start']}-{s2['set_end']}）重叠 {overlap} 分钟"
                        )
                    elif -10 <= overlap <= 0 and s1.get("stage") != s2.get("stage"):
                        clashes.append(
                            f"{day} 极限换场：{s1['artist']}（{s1.get('stage', '')}）与 {s2['artist']}（{s2.get('stage', '')}）间隔仅 {-overlap} 分钟"
                        )

        grp["day_breakdown"] = [
            {"day_date": d, "followed_artists": arts, "count": len(arts)}
            for d, arts in sorted(day_artists.items())
        ]
        grp["best_single_day"] = (
            f"推荐买 {best_day} 单日票（含 {best_count} 组关注乐队：{'、'.join(day_artists[best_day])}）"
            if best_day and best_count > 0
            else f"共关联 {len(grp['matched_artists'])} 组关注音乐人"
        )
        grp["clashes"] = clashes
        results.append(grp)

    results.sort(key=lambda g: g.get("show_time", ""))
    return results


def compute_stub_wall_stats(concerts: list[dict[str, Any]]) -> dict[str, Any]:
    """Computes summary metrics for attended & purchased concerts on the Ticket-Stub Archive Wall."""
    attended = [c for c in concerts if c.get("status") == "attended"]
    cities = sorted({c["city"] for c in attended if c.get("city")})
    total_spent = 0
    ratings: list[int] = []
    artist_counter: collections.Counter[str] = collections.Counter()

    for c in attended:
        paid = int(c.get("actual_paid_yuan") or 0)
        if paid <= 0 and c.get("price_text"):
            m = re.search(r"(\d{2,4})", c["price_text"])
            if m:
                paid = int(m.group(1))
        total_spent += paid
        if int(c.get("venue_rating") or 0) > 0:
            ratings.append(int(c["venue_rating"]))
        if c.get("artist_name"):
            artist_counter[c["artist_name"]] += 1

    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
    top_artists = [{"name": k, "count": v} for k, v in artist_counter.most_common(5)]
    return {
        "attended_count": len(attended),
        "unlocked_cities": cities,
        "unlocked_city_count": len(cities),
        "total_spent_yuan": total_spent,
        "avg_venue_rating": avg_rating,
        "top_artists": top_artists,
    }


# ---------------- Major China & HK/Macau Arena Guides & Cross-City Budget ----------------

VENUE_GUIDES: list[dict[str, Any]] = [
    {
        "keywords": ["梅赛德斯", "梅奔"],
        "venue_name": "梅赛德斯-奔驰文化中心（上海）",
        "best_seats": "二层正中 215–220 区（视听黄金位，舞美与声像最均衡）",
        "avoid_tip": "五层山顶区坡度较陡，恐高慎选；内场后区无阶梯容易被前排举灯牌遮挡",
        "transit_tip": "散场步行 5 分钟至地铁 8 号线中华艺术宫站（留意约 22:50 末班车）",
    },
    {
        "keywords": ["上海体育场", "八万人"],
        "venue_name": "上海体育场（上海）",
        "best_seats": "一层/二层东西看台中前段，视野开阔且风噪较小",
        "avoid_tip": "露天体育场避开极端侧看台，雨天需准备折叠雨衣（场馆禁带长柄伞）",
        "transit_tip": "散场分流至地铁 1/4 号线上海体育馆站或 11 号线上海游泳馆站",
    },
    {
        "keywords": ["鸟巢", "国家体育场"],
        "venue_name": "国家体育场·鸟巢（北京）",
        "best_seats": "二层正对舞台的西/东侧中段看台（声画同步佳、性价比特高）",
        "avoid_tip": "三层极高侧位存在轻微混响延迟；大型场安检排队较久建议提前 75 分钟入场",
        "transit_tip": "散场优先走地铁 8 号线奥林匹克公园站或 15 号线安立路站",
    },
    {
        "keywords": ["五棵松", "华熙"],
        "venue_name": "华熙LIVE·五棵松场馆（北京）",
        "best_seats": "105–112 区低层看台（距离舞台近、室内声场紧实通透）",
        "avoid_tip": "四层侧看台受大屏角度限制，优先选中轴区域",
        "transit_tip": "散场无缝接驳地铁 1 号线五棵松站，周边商业体夜宵选择极多",
    },
    {
        "keywords": ["大莲花", "杭州奥体"],
        "venue_name": "杭州奥体中心（大莲花 / 体育馆）",
        "best_seats": "二层中轴 208–214 区（全息大屏与沉浸灯海体验极佳）",
        "avoid_tip": "内场后区地势较平，身高不占优势建议优先选低层看台",
        "transit_tip": "散场步行至地铁 6/7 号线奥体中心站，安可尾声可提前 3 分钟靠近出口避高峰",
    },
    {
        "keywords": ["南京奥体"],
        "venue_name": "南京奥体中心（南京）",
        "best_seats": "室内体育馆二层中前排坡度友好，全程无前排遮挡",
        "avoid_tip": "体育场夏秋季开场前西看台背阳更舒适，东看台傍晚易受夕阳直射",
        "transit_tip": "散场步行约 10 分钟至地铁 2 号线奥体东站或 10 号线元通站",
    },
    {
        "keywords": ["广州奥林匹克", "广州奥体"],
        "venue_name": "广东奥林匹克体育中心（广州）",
        "best_seats": "一层看台正对中轴中前排，声场集中且价格比内场友好",
        "avoid_tip": "华南潮湿多阵雨，室外场务必常备一次性雨衣与防蚊喷雾",
        "transit_tip": "散场至地铁 4/21 号线黄村站，如遇大客流可乘演出接驳公交至天河公园",
    },
    {
        "keywords": ["宝能", "广州国际体育演艺"],
        "venue_name": "广州宝能国际体育演艺中心（广州）",
        "best_seats": "珠三角顶级室内声学场馆，连三层中轴听感也相当清晰",
        "avoid_tip": "距市区车程约 40 分钟，跨城返程请预留充足交通缓冲",
        "transit_tip": "地铁 6 号线萝岗站 C 口出站即达，散场有加开接驳巴士",
    },
    {
        "keywords": ["大运中心"],
        "venue_name": "深圳大运中心（深圳）",
        "best_seats": "看台中轴前 10 排视野兼顾舞台灯光与近景特写",
        "avoid_tip": "体育场开阔风大，冬季夜场建议多带一件防风外套",
        "transit_tip": "地铁 16 号线大运中心站步行 8 分钟，大型演唱会通常配福田/罗湖散场直通大巴",
    },
    {
        "keywords": ["B10"],
        "venue_name": "B10 现场（深圳）",
        "best_seats": "全站席：调音台正前方 2–4 米为声场甜点区，鼓组与人声层次最佳",
        "avoid_tip": "热门专场建议开演前 45 分钟到华侨城创意园排队占前中区",
        "transit_tip": "散场步行 6 分钟至地铁 2 号线侨城北站，周边清吧与餐饮丰富",
    },
    {
        "keywords": ["启德"],
        "venue_name": "香港启德体育园主场馆（香港）",
        "best_seats": "五万人可开合顶盖新主场馆，下层侧中段看台视角稳、声学反射干净",
        "avoid_tip": "香港室内场馆冷气偏足，建议随身带轻薄外套；提前确认港澳通行证签注有效期",
        "transit_tip": "港铁屯马线启德站 / 宋皇台站步行 10 分钟；次日可由西九龙站乘高铁直返内地",
    },
    {
        "keywords": ["红磡", "紅磡", "香港体育馆", "香港體育館"],
        "venue_name": "红磡香港体育馆·红馆（香港）",
        "best_seats": "经典四面台拉近全场距离，红闸/绿闸 10–20 行（中段）公认最值",
        "avoid_tip": "红馆山顶位虽陡但距舞台实际直线距离比内地大体育场近得多，依然值得冲",
        "transit_tip": "港铁东铁线红磡站步行 3 分钟直达，搭东铁线 45 分钟即可直达罗湖/落马洲口岸",
    },
    {
        "keywords": ["银河综艺", "銀河綜藝"],
        "venue_name": "澳门银河综艺馆（澳门）",
        "best_seats": "港澳顶级室内场馆，一层看台坡度科学，几乎无视线死角",
        "avoid_tip": "请提前备好港澳通行证及有效签注，并留意横琴/拱北口岸通关高峰",
        "transit_tip": "可乘澳门轻轨排角站或银河免费发财车直达横琴口岸（24 小时通关）/ 拱北口岸",
    },
    {
        "keywords": ["亚洲国际博览馆", "亞洲國際博覽館", "亚博馆", "亞博館"],
        "venue_name": "香港亚洲国际博览馆 Arena（香港）",
        "best_seats": "欧美/日韩巡演高频主场，Block A/B 阶梯看台视角远优于平地后区",
        "avoid_tip": "平地站席后段身高不占优容易遮挡；散场往港岛/九龙建议提前买好机场快线来回优惠票",
        "transit_tip": "港铁机场快线博览馆站直达（28 分钟到中环），或散场乘直通跨境巴士直达深圳湾口岸",
    },
    {
        "keywords": ["威尼斯人", "金光综艺"],
        "venue_name": "澳门威尼斯人综艺馆（澳门）",
        "best_seats": "1.5 万人全视角室内馆，200 段中轴看台观演距离近、混响控制优秀",
        "avoid_tip": "周末房态紧张，官宣过审即建议锁定氹仔或横琴口岸酒店",
        "transit_tip": "散场可乘免费发财车往返横琴/关闸口岸，或步行至轻轨路氹东站",
    },
    {
        "keywords": ["东方体育中心", "东体"],
        "venue_name": "浦发银行东方体育中心（上海）",
        "best_seats": "四面台或三面台设计视野极近，二层正中看台（208–216）性价比超高",
        "avoid_tip": "紧邻前滩商圈，开演前 1 小时周边停车位紧俏，强烈建议地铁出行",
        "transit_tip": "地铁 6/8/11 号线东方体育中心站出站步行 5 分钟即达，三线换乘散场极快",
    },
    {
        "keywords": ["金融城", "大魔方"],
        "venue_name": "成都金融城演艺中心·大魔方（成都）",
        "best_seats": "西南顶级室内声学馆，二层中轴声场通透干净，适合日系/欧美专场",
        "avoid_tip": "内场前排虽近但仰视角较大，看整体舞台灯光优选看台前 10 排",
        "transit_tip": "地铁 1 号线孵化园站或 9 号线心岛站步行 8 分钟直达",
    },
    {
        "keywords": ["东安湖"],
        "venue_name": "成都东安湖体育公园（成都）",
        "best_seats": "室内体育馆二层看台视线通透；体育场优先选中轴下层看台",
        "avoid_tip": "距主城区稍远，切勿散场后临时打车（排队极久），优先搭乘官方接驳线",
        "transit_tip": "散场乘官方接驳大巴直达地铁 2 号线连山坡站或界牌站",
    },
    {
        "keywords": ["凤凰山"],
        "venue_name": "成都凤凰山体育公园（成都）",
        "best_seats": "专业演艺级声场与大屏配置，中轴看台体验堪比内场前排",
        "avoid_tip": "热门场次地铁站入口临时限流，错峰 10 分钟离场体验更从容",
        "transit_tip": "地铁 5 号线杜家碾站出站步行即达，直达市区极其方便",
    },
    {
        "keywords": ["南沙音乐秀场", "草莓", "音乐节"],
        "venue_name": "户外音乐节双舞台（通用指南）",
        "best_seats": "主舞台 FOH 调音台两侧 15 米内声压最均衡，且便于快速转场至副舞台",
        "avoid_tip": "双舞台步行转场约需 8–12 分钟；务必避开舞台音箱正前方 5 米以内以保护听力",
        "transit_tip": "提前查好音乐节官方散场接驳车发车末班时间，并自备充电宝与便携雨衣",
    },
]

CITY_MAP_NODES: list[dict[str, Any]] = [
    {"city": "长春", "region": "north_nw", "x": 598, "y": 92, "lx": -13, "ly": 4, "anchor": "end", "tier": 2, "lat": 43.82, "lon": 125.32},
    {"city": "北京", "region": "jjj", "x": 494, "y": 144, "lx": 15, "ly": -8, "anchor": "start", "tier": 1, "lat": 39.90, "lon": 116.40},
    {"city": "天津", "region": "jjj", "x": 524, "y": 162, "lx": 12, "ly": 5, "anchor": "start", "tier": 2, "lat": 39.08, "lon": 117.20},
    {"city": "石家庄", "region": "jjj", "x": 462, "y": 178, "lx": -12, "ly": 4, "anchor": "end", "tier": 2, "lat": 38.04, "lon": 114.51},
    {"city": "济南", "region": "north_nw", "x": 520, "y": 198, "lx": -12, "ly": 4, "anchor": "end", "tier": 2, "lat": 36.65, "lon": 117.12},
    {"city": "青岛", "region": "north_nw", "x": 576, "y": 196, "lx": 12, "ly": 4, "anchor": "start", "tier": 2, "lat": 36.07, "lon": 120.38},
    {"city": "郑州", "region": "central", "x": 462, "y": 230, "lx": -12, "ly": 4, "anchor": "end", "tier": 2, "lat": 34.75, "lon": 113.62},
    {"city": "西安", "region": "north_nw", "x": 384, "y": 236, "lx": -12, "ly": 4, "anchor": "end", "tier": 2, "lat": 34.34, "lon": 108.94},
    {"city": "南京", "region": "jzh", "x": 534, "y": 252, "lx": -14, "ly": -4, "anchor": "end", "tier": 2, "lat": 32.06, "lon": 118.80},
    {"city": "合肥", "region": "jzh", "x": 506, "y": 274, "lx": -12, "ly": 12, "anchor": "end", "tier": 2, "lat": 31.82, "lon": 117.23},
    {"city": "苏州", "region": "jzh", "x": 574, "y": 254, "lx": 0, "ly": -13, "anchor": "middle", "tier": 2, "lat": 31.30, "lon": 120.58},
    {"city": "上海", "region": "jzh", "x": 608, "y": 272, "lx": 16, "ly": 4, "anchor": "start", "tier": 1, "lat": 31.23, "lon": 121.47},
    {"city": "杭州", "region": "jzh", "x": 572, "y": 298, "lx": -13, "ly": 6, "anchor": "end", "tier": 2, "lat": 30.27, "lon": 120.15},
    {"city": "宁波", "region": "jzh", "x": 608, "y": 318, "lx": 12, "ly": 5, "anchor": "start", "tier": 2, "lat": 29.87, "lon": 121.55},
    {"city": "武汉", "region": "central", "x": 462, "y": 284, "lx": -14, "ly": 4, "anchor": "end", "tier": 2, "lat": 30.59, "lon": 114.30},
    {"city": "长沙", "region": "central", "x": 456, "y": 324, "lx": -12, "ly": 4, "anchor": "end", "tier": 2, "lat": 28.23, "lon": 112.94},
    {"city": "成都", "region": "cy", "x": 302, "y": 290, "lx": -15, "ly": 4, "anchor": "end", "tier": 2, "lat": 30.57, "lon": 104.07},
    {"city": "重庆", "region": "cy", "x": 354, "y": 312, "lx": 14, "ly": 5, "anchor": "start", "tier": 2, "lat": 29.56, "lon": 106.55},
    {"city": "厦门", "region": "fujian", "x": 558, "y": 356, "lx": 12, "ly": 4, "anchor": "start", "tier": 2, "lat": 24.48, "lon": 118.09},
    {"city": "广州", "region": "gba", "x": 468, "y": 374, "lx": -15, "ly": -4, "anchor": "end", "tier": 1, "lat": 23.13, "lon": 113.26},
    {"city": "深圳", "region": "gba", "x": 506, "y": 388, "lx": 16, "ly": -2, "anchor": "start", "tier": 1, "lat": 22.54, "lon": 114.06},
    {"city": "香港", "region": "gba", "x": 524, "y": 416, "lx": 16, "ly": 6, "anchor": "start", "tier": 0, "lat": 22.32, "lon": 114.17},
    {"city": "澳门", "region": "gba", "x": 472, "y": 416, "lx": -15, "ly": 6, "anchor": "end", "tier": 0, "lat": 22.20, "lon": 113.54},
    {"city": "澄迈", "region": "gba", "x": 416, "y": 424, "lx": -12, "ly": 4, "anchor": "end", "tier": 2, "lat": 19.74, "lon": 110.00},
]

_CITY_GEO_LOOKUP: dict[str, tuple[float, float, int]] = {
    n["city"]: (float(n["lat"]), float(n["lon"]), int(n["tier"])) for n in CITY_MAP_NODES
}


def get_venue_guide(venue: str, title: str = "") -> dict[str, str] | None:
    """Returns curated seating, acoustics, and post-show transit tips for major China & HK/Macau venues."""
    hay = f"{venue or ''} {title or ''}"
    for guide in VENUE_GUIDES:
        if any(kw in hay for kw in guide["keywords"]):
            return {
                "venue_name": guide["venue_name"],
                "best_seats": guide["best_seats"],
                "avoid_tip": guide["avoid_tip"],
                "transit_tip": guide["transit_tip"],
            }
    return None


def _estimate_mid_ticket_yuan(price_text: str) -> int:
    """Extracts a realistic mid-tier ticket budget in CNY from ¥ / HK$ / MOP$ strings."""
    if not price_text:
        return 680
    nums = sorted({int(m) for m in re.findall(r"\d{3,4}", price_text)})
    if not nums:
        return 680
    if len(nums) == 1:
        mid = nums[0]
    elif len(nums) == 2:
        mid = int(round((nums[0] + nums[1]) / 2.0))
    else:
        mid = nums[len(nums) // 2]
    if "HK" in price_text.upper() or "港币" in price_text or "MOP" in price_text.upper():
        mid = int(round(mid * 0.92))
    return max(180, min(3600, mid))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def estimate_weekend_trip_budget(home_city: str, concert: dict[str, Any]) -> dict[str, Any]:
    """Computes a practical weekend cross-city concert budget (ticket + 12306 HSR round-trip + 1-night hotel)."""
    origin = normalize_city_name(home_city or "上海") or "上海"
    dest = normalize_city_name(concert.get("city") or "") or "上海"
    ticket_mid = _estimate_mid_ticket_yuan(str(concert.get("price_text") or ""))

    if origin == dest:
        return {
            "is_cross_city": False,
            "origin": origin,
            "destination": dest,
            "hsr_hours_one_way": 0.0,
            "hsr_roundtrip_yuan": 0,
            "hotel_1night_yuan": 0,
            "ticket_mid_yuan": ticket_mid,
            "total_weekend_yuan": ticket_mid,
            "transport_note": f"同城观演（{origin}），无需跨城高铁与住宿",
        }

    olat, olon, _ = _CITY_GEO_LOOKUP.get(origin, (31.23, 121.47, 1))
    dlat, dlon, d_tier = _CITY_GEO_LOOKUP.get(dest, (30.59, 114.30, 2))
    air_km = _haversine_km(olat, olon, dlat, dlon)
    rail_km = max(35.0, air_km * 1.18)

    # Real Chinese HSR averages ~220-245 km/h including station stops; short links <80km ~0.3-0.5h
    hours_one_way = round(max(0.3, min(11.5, rail_km / 225.0)), 1)
    one_way_fare = int(round(max(45.0, min(1180.0, rail_km * 0.45)) / 10.0) * 10)
    hsr_roundtrip = one_way_fare * 2

    if d_tier == 0:  # 香港 / 澳门
        hotel_night = 820
    elif d_tier == 1:  # 北上广深
        hotel_night = 460
    else:
        hotel_night = 340

    return {
        "is_cross_city": True,
        "origin": origin,
        "destination": dest,
        "hsr_hours_one_way": hours_one_way,
        "hsr_roundtrip_yuan": hsr_roundtrip,
        "hotel_1night_yuan": hotel_night,
        "ticket_mid_yuan": ticket_mid,
        "total_weekend_yuan": ticket_mid + hsr_roundtrip + hotel_night,
        "transport_note": f"高铁单程约 {hours_one_way} 小时 · 往返二等座约 ¥{hsr_roundtrip} · 周边住宿参考 ¥{hotel_night}/晚",
    }
