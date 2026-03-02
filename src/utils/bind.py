from .file_db import FileDB, get_file_db
from ..handlers import assert_and_reply, ReplyException, HandlerContext
from ..config import get_global_config, Config
from .lifecycle import on_initialize
from astrbot.api import logger
from os.path import join as pjoin

_profile_db: FileDB = None

config: Config | None = None

@on_initialize(order=30)
def initialize_profile():
    global _profile_db, config
    config = get_global_config()
    profile_db_path = pjoin(config.data_path, "profile")
    _profile_db = get_file_db(profile_db_path)

# 获取用户绑定的账号数量
def get_player_bind_count(region: str, qid: int) -> int:
    bind_list: dict[str, list[str]] = _profile_db.get("bind_list", {}).get(region, {})
    uids = bind_list.get(str(qid), [])
    return len(uids)

# 获取qq用户绑定的游戏id，如果qid=None则使用ctx.uid_arg获取用户id，index=None获取主绑定账号
def get_player_bind_id(ctx:HandlerContext, qid: int = None, check_bind=True, index: int | None=None) -> str:
    bind_list: dict[str, list[str]] = _profile_db.get("bind_list", {}).get(ctx.region, {})
    main_bind_list: dict[str, str] = _profile_db.get("main_bind_list", {}).get(ctx.region, {})

    def get_uid_by_index(qid: str, index: int) -> str | None:
        uids = bind_list.get(qid, [])
        if not uids:
            return None
        assert_and_reply(0 <= index < len(uids), f"指定的账号序号大于已绑定的{ctx.region}账号数量({len(uids)})")
        return uids[index]

    # 指定qid/没有ctx.uid_arg的情况则直接获取qid绑定的账号
    if qid:
        if index is None:
            uid = main_bind_list.get(qid, None) or get_uid_by_index(qid, 0)
        else:
            uid = get_uid_by_index(qid, index)
    else:
        index = 0
        for token in ctx.get_args().split():
            if token.startswith('u'):
                index = int(token[1:]) - 1
                break
        uid = get_uid_by_index(ctx.event.get_sender_id(), index)
    if check_bind and uid is None:
        raise ReplyException(f"请使用\"/{ctx.region}绑定 你的游戏ID\"绑定账号")
    assert_and_reply(not check_uid_in_blacklist(uid), f"该游戏ID({uid})已被拉入黑名单")
    return uid

# 获取某个id在用户绑定的账号中的索引，找不到返回None
def get_player_bind_id_index(region, qid: str, uid: str) -> int | None:
    bind_list: dict[str, list[str]] = _profile_db.get("bind_list", {}).get(region, {})
    uids = bind_list.get(str(qid), [])
    try:
        return uids.index(str(uid))
    except ValueError:
        return None
def add_player_bind_id(region: str, qid: str, uid, set_main: bool):
    all_bind_list: dict[str, list[str]] = _profile_db.get("bind_list", {})
    all_main_bind_list: dict[str, str] = _profile_db.get("main_bind_list", {})
    qid = str(qid)
    additional_info = ""

    if region not in all_bind_list:
        all_bind_list[region] = {}
    if region not in all_main_bind_list:
        all_main_bind_list[region] = {}

    uids = all_bind_list[region].get(qid, [])
    if uid not in uids:
        total_bind_limit = config.sekaiprofile.bind_limit.get(region, 0)
        if len(uids) >= total_bind_limit:
            while len(uids) >= total_bind_limit:
                uids.pop(0)
            additional_info += f"你绑定的{region}账号数量已达上限({total_bind_limit})，已自动解绑最早绑定的账号\n"
        uids.append(uid)
        
        all_bind_list[region][qid] = uids
        _profile_db.set("bind_list", all_bind_list)
        logger.info(f"为 {qid} 绑定 {region}账号: {uid}")
    else:
        logger.info(f"为 {qid} 绑定 {region}账号: {uid} 已存在，跳过绑定")

    if set_main:
        all_main_bind_list[region][qid] = uid
        _profile_db.set("main_bind_list", all_main_bind_list)
        uid_index = uids.index(uid) + 1
        additional_info += f"已将该账号u{uid_index}设为你的{region}主账号\n"
        logger.info(f"为 {qid} 设定 {region}主账号: {uid}")

    return additional_info.strip()


# 使用索引解除绑定，返回信息，index为None则解除主绑定账号
def remove_player_bind_id(region:str, qid: str, index: int | None) -> str:
    all_bind_list: dict[str, list[str]] = _profile_db.get("bind_list", {})
    all_main_bind_list: dict[str, str] = _profile_db.get("main_bind_list", {})
    qid = str(qid)
    ret_info = ""

    if region not in all_bind_list:
        all_bind_list[region] = {}
    if region not in all_main_bind_list:
        all_main_bind_list[region] = {}

    uids = all_bind_list[region].get(qid, [])
    assert_and_reply(uids, f"你还没有绑定任何{region}账号")
    assert_and_reply(index < 1e9, f"需要指定账号序号（按绑定时间顺序）而不是账号ID")

    if index is not None:
        assert_and_reply(0 <= index < len(uids), f"指定的账号序号大于已绑定的{region}账号数量({len(uids)})")
        removed_uid = uids.pop(index)
    else:
        main_bind_uid = get_player_bind_id(region, qid)
        uids.remove(main_bind_uid)
        removed_uid = main_bind_uid

    all_bind_list[region][qid] = uids
    _profile_db.set("bind_list", all_bind_list)
    logger.info(f"为 {qid} 解除绑定 {region}账号: {removed_uid}")

    ret_info += f"已解除绑定你的{region}账号{process_hide_uid(region, removed_uid, keep=6)}\n"

    if all_main_bind_list[region].get(qid, None) == removed_uid:
        if uids:
            all_main_bind_list[region][qid] = uids[0]
            ret_info += f"已将你的{region}主账号切换为当前第一个账号({process_hide_uid(region, uids[0], keep=6)})\n"
            logger.info(f"为 {qid} 切换 {region}主账号: {uids[0]}")
        else:
            all_main_bind_list[region].pop(qid, None)
            ret_info += f"你目前没有绑定任何{region}账号，主账号已清除\n"
            logger.info(f"为 {qid} 清除 {region}主账号")
        _profile_db.set("main_bind_list", all_main_bind_list)

    return ret_info.strip()

# 使用索引修改主绑定账号，返回信息
def set_player_main_bind_id(region: str, qid: str, index: int) -> str:
    all_bind_list: dict[str, list[str]] = _profile_db.get("bind_list", {})
    all_main_bind_list: dict[str, str] = _profile_db.get("main_bind_list", {})
    qid = str(qid)

    if region not in all_bind_list:
        all_bind_list[region] = {}
    if region not in all_main_bind_list:
        all_main_bind_list[region] = {}

    uids = all_bind_list[region].get(qid, [])
    assert_and_reply(uids, f"你还没有绑定任何{region}账号")
    assert_and_reply(index < 1e9, f"需要指定账号序号（按绑定时间顺序）而不是账号ID")
    assert_and_reply(0 <= index < len(uids), f"指定的账号序号大于已绑定的{region}账号数量({len(uids)})")

    new_main_uid = uids[index]
    all_main_bind_list[region][qid] = new_main_uid
    _profile_db.set("main_bind_list", all_main_bind_list)

    return f"已将你的{region}主账号修改为{process_hide_uid(region, new_main_uid, keep=6)}"

# 使用索引交换账号顺序
def swap_player_bind_id(region, qid: str, index1: int, index2: int) -> str:
    all_bind_list: dict[str, str | list[str]] = _profile_db.get("bind_list", {})
    
    if region not in all_bind_list:
        all_bind_list[region] = {}

    uids = all_bind_list[region].get(qid, [])
    assert_and_reply(uids, f"你还没有绑定任何{region}账号")
    assert_and_reply(index1 < 1e9, f"需要指定账号序号（按绑定时间顺序）而不是账号ID")
    assert_and_reply(index2 < 1e9, f"需要指定账号序号（按绑定时间顺序）而不是账号ID")
    assert_and_reply(0 <= index1 < len(uids), f"指定的账号序号1大于已绑定的{region}账号数量({len(uids)})")
    assert_and_reply(0 <= index2 < len(uids), f"指定的账号序号2大于已绑定的{region}账号数量({len(uids)})")

    uids[index1], uids[index2] = uids[index2], uids[index1]
    all_bind_list[region][qid] = uids
    _profile_db.set("bind_list", all_bind_list)

    return f"""
已将你绑定的{region}第{index1 + 1}个账号序号和第{index2 + 1}个账号交换顺序
该指令仅影响索引查询(u{index1 + 1}、u{index2 + 1})，修改默认查询账号请使用"/主账号"
""".strip()

# 检测游戏id是否在黑名单中
def check_uid_in_blacklist(uid: str) -> bool:
    blacklist = _profile_db.get("blacklist", [])
    return uid in blacklist

# 用户是否隐藏id
def is_user_hide_id(region: str, qid: str) -> bool:
    hide_list = _profile_db.get("hide_id_list", {}).get(region, [])
    return qid in hide_list

# 如果ctx的用户隐藏id则返回隐藏的uid，否则原样返回
def process_hide_uid(region: str, qid: str, uid: int, keep: int=0) -> str:
    if is_user_hide_id(region, qid):
        if keep:
            return "*" * (16 - keep) + str(uid)[-keep:]
        return "*" * 16
    return uid
