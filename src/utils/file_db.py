import os, orjson
from copy import deepcopy
from .task import repeat_with_interval
from ..config import get_global_config, Config
from .lifecycle import on_initialize, on_terminate
from astrbot.api import logger

FILE_DB_SAVE_INTERVAL = 5
config: Config | None = None

def load_json(file_path: str) -> dict:
    with open(file_path, 'rb') as file:
        return orjson.loads(file.read())
    
def dump_json(data: dict, file_path: str, indent: bool = True) -> None:
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    # 首先保存到临时文件，保存成功后再替换原文件，避免写入过程中程序崩溃导致文件损坏
    tmp_path = f"{file_path}.tmp"
    with open(tmp_path, 'wb') as file:
        buffer = orjson.dumps(data, option=orjson.OPT_INDENT_2 if indent else 0)
        file.write(buffer)
    os.replace(tmp_path, file_path)
    try: os.remove(tmp_path)
    except: pass

@on_initialize(order=10)
def initialize_file_db():
    global FILE_DB_SAVE_INTERVAL, config
    config = get_global_config()
    FILE_DB_SAVE_INTERVAL = config.file_db_save_interval

class FileDB:
    _updated_dbs: set['FileDB'] = set()

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.data = {}
        self.loaded = False

    def __hash__(self) -> int:
        return hash(self.path)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FileDB):
            return False
        return self.path == other.path

    def _ensure_load(self):
        if self.loaded:
            return
        try:
            self.data = load_json(self.path)
            logger.debug(f'加载数据库 {self.path} 成功')
        except:
            logger.debug(f'加载数据库 {self.path} 失败 使用空数据')
            self.data = {}
        self.loaded = True

    def _after_change(self):
        if FILE_DB_SAVE_INTERVAL <= 0:
            self.save()
        else:
            FileDB._updated_dbs.add(self)

    def _get_last_dict_and_key(self, key: str, create_path: bool = False) -> tuple[dict | None, str | None]:
        """
        - 从多层key获取最后一层dict和key
        - 设置create_path时找不到会创建直到last_dict的路径，否则返回(None,None)
        - 设置create_path后需要自行保证_after_change被调用
        """
        assert isinstance(key, str), f'key: "{key}" 必须是字符串，当前类型: {type(key)}'
        self._ensure_load()
        key = key.replace("\\.", "&#46;")
        keys = key.split('.')
        last_dict = self.data
        last_key = keys.pop()
        for k in keys:
            k = k.replace("&#46;", ".")
            if k not in last_dict or not isinstance(last_dict[k], dict):
                if create_path:
                    last_dict[k] = {}
                else:
                    return None, None
            last_dict = last_dict[k]
        return last_dict, last_key
    

    def keys(self) -> set[str]:
        """
        - 获取所有第一层key的集合
        """
        self._ensure_load()
        return self.data.keys()

    def save(self):
        """
        - 保存数据到文件，在修改后会被自动调用，一般不需要手动调用
        """
        try:
            self._ensure_load()
            dump_json(self.data, self.path)
            logger.debug(f'保存数据库 {self.path}')
        except:
            logger.error(f'保存数据库 {self.path} 失败', exc_info=True)

    def get(self, key: str, default = None):
        """
        - 获取某个key的值，找不到返回default
        - 支持多层key，用点号分隔，如"a.b.c"
        - 直接返回缓存对象，若要进行修改又不影响DB内容则必须自行deepcopy，或者使用get_copy方法
        """
        self._ensure_load()
        d, k = self._get_last_dict_and_key(key)
        if d is None:
            return default
        return d.get(k, default)

    def get_copy(self, key: str, default = None):
        """
        - 获取某个key的值的深拷贝，找不到返回default的深拷贝
        - 支持多层key，用点号分隔，如"a.b.c"
        """
        self._ensure_load()
        d, k = self._get_last_dict_and_key(key)
        if d is None:
            return deepcopy(default)
        return deepcopy(d.get(k, default))

    def set(self, key: str, value: any):
        """
        - 设置某个key的值，会自动保存
        - 支持多层key，用点号分隔，如"a.b.c"
        """
        self._ensure_load()
        logger.debug(f'设置数据库 {self.path} {key}')
        d, k = self._get_last_dict_and_key(key, create_path=True)
        d[k] = value
        self._after_change()

    def delete(self, key: str):
        """
        - 删除某个key的值，会自动保存
        - 支持多层key，用点号分隔，如"a.b.c"
        """
        self._ensure_load()
        logger.debug(f'删除数据库 {self.path} {key}')
        d, k = self._get_last_dict_and_key(key)
        if d is not None and k in d:
            del d[k]
            self._after_change()

    @classmethod
    def save_all_changed(cls):
        """
        - 保存所有修改过的数据库
        """
        for db in list(cls._updated_dbs):
            db.save()
        cls._updated_dbs.clear()


@repeat_with_interval(FILE_DB_SAVE_INTERVAL, '保存文件数据库')
async def _save_changed_file_dbs():
    FileDB.save_all_changed()

@on_terminate(order=10)
def terminate_file_db():
    FileDB.save_all_changed()


_file_dbs: dict[str, FileDB] = {}
def get_file_db(path: str) -> FileDB:
    global _file_dbs
    if path not in _file_dbs:
        _file_dbs[path] = FileDB(path)
    return _file_dbs[path]
