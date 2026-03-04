from astrbot.api import AstrBotConfig, logger
from pydantic import BaseModel

class SekaiRanking(BaseModel):
    base_url: str = "https://sekairanking.exmeaning.com"
    cache_duration: int = 1800
    page_size: tuple | list = (1080,1080)
    timeout: int = 60
    all_ranks: list =  [
            50, 100, 200, 300, 400, 500,
            1000, 2000, 3000, 4000, 5000,
            10000,
        ]
    allow_regions: list = ["cn", "jp"]

class SekaiProfile(BaseModel):
    base_url: str = "https://sekaiprofile.exmeaning.com/profile/{user_id}?token={token}"
    token: str = ""
    bind_limit: dict = {"cn":3,"jp":3}
    
class Config(BaseModel):
    data_path: str = "data/plugin_data/moesekai"
    file_db_save_interval: int = 5
    regions: list = ['cn', 'jp']
    sekairanking: SekaiRanking = SekaiRanking()
    sekaiprofile: SekaiProfile = SekaiProfile()


global_config: Config = Config()

def set_global_config(config: AstrBotConfig) -> None:
    global global_config
    try:
        # model_validate 可以接受 dict 或者对象
        # 它会自动将嵌套的字典转换为 SekaiRanking 和 SekaiProfile 实例
        global_config = Config.model_validate(config)
    except Exception as e:
        # 处理验证失败的情况
        logger.error(f"配置加载失败: {e}")
        raise


def get_global_config() -> Config:
    if global_config is None:
        raise RuntimeError("Global config is not initialized yet.")
    return global_config
