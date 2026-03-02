from datetime import datetime, timedelta
import os 
from os.path import join as pjoin
from typing import Tuple
from uuid import uuid4
import glob
import shutil
from astrbot.api import logger
from .task import repeat_with_interval
from ..config import get_global_config, Config
from .lifecycle import on_initialize


TEMP_FILE_DIR =  'data/utils/tmp'
config: Config | None = None

@on_initialize(order=20)
def initialize_tempfile():
    global TEMP_FILE_DIR, config
    config = get_global_config()
    TEMP_FILE_DIR = pjoin(config.data_path, "tmp")

_tmp_files_to_remove: list[Tuple[str, datetime]] = []


def create_folder(folder_path) -> str:
    """
    创建文件夹，返回文件夹路径
    """
    folder_path = str(folder_path)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path

def create_parent_folder(file_path) -> str:
    """
    创建文件所在的文件夹，返回文件路径
    """
    parent_folder = os.path.dirname(file_path)
    create_folder(parent_folder)
    return file_path

def remove_folder(folder_path):
    folder_path = str(folder_path)
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)

def remove_file(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)

def rand_filename(ext: str) -> str:
    if ext.startswith('.'):
        ext = ext[1:]
    return f'{uuid4()}.{ext}'

class TempFilePath:
    """
    临时文件路径
    remove_after为None表示使用后立即删除，否则延时删除
    """
    def __init__(self, ext: str, remove_after: timedelta = None):
        self.ext = ext
        self.path = os.path.abspath(pjoin(TEMP_FILE_DIR, rand_filename(ext)))
        self.remove_after = remove_after
        create_parent_folder(self.path)

    def __enter__(self) -> str:
        return self.path
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.remove_after is None:
            # utils_logger.info(f'删除临时文件 {self.path}')
            remove_file(self.path)
        else:
            _tmp_files_to_remove.append((self.path, datetime.now() + self.remove_after))



@repeat_with_interval(60, '清除临时文件')
async def _():
    """
    定期删除过期的临时文件
    """
    global _tmp_files_to_remove
    now = datetime.now()
    new_list = []
    for path, remove_time in _tmp_files_to_remove:
        if now >= remove_time:
            try:
                if os.path.isfile(path):
                    remove_file(path)
                elif os.path.isdir(path):
                    remove_folder(path)
            except:
                logger.error(f'删除临时文件 {path} 失败')
        else:
            new_list.append((path, remove_time))
    _tmp_files_to_remove = new_list

    # 强制清理超过一天的文件
    files = glob.glob(pjoin(TEMP_FILE_DIR, '*'))
    for file in files:
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(file))
            if now - mtime > timedelta(days=1):
                if os.path.isfile(file):
                    remove_file(file)
                elif os.path.isdir(file):
                    remove_folder(file)
        except:
            logger.error(f'删除临时文件 {file} 失败')
