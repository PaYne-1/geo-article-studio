"""Hidden API credential intake and persistent user-environment storage."""
import getpass
import os
import sys

NAMES={'image':'GEO_IMAGE_API_KEY','text':'GEO_TEXT_API_KEY'}

def read_user_environment(name):
    """Read one persisted Windows user environment value without printing it."""
    if os.name!='nt':
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment',0,winreg.KEY_READ) as key:
            value,_=winreg.QueryValueEx(key,name)
    except OSError:
        return None
    return value if isinstance(value,str) and value else None

def hydrate_known_environment():
    """Make persisted GEO credentials available to each newly started CLI process."""
    loaded=[]
    for name in NAMES.values():
        value=read_user_environment(name)
        if value:
            os.environ[name]=value
            loaded.append(name)
    return loaded

def persist_user_environment(name,value):
    if os.name!='nt':
        raise ValueError('当前宿主没有通用安全凭据写入器；请使用宿主安全凭据存储后重新运行配置检查')
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,'Environment',0,winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
    os.environ[name]=value
    try:
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF,0x001A,0,'Environment',0x0002,5000,None)
    except (AttributeError,OSError):
        pass
    return 'windows_user_environment'

def configure(kind,model,*,key_stdin=False):
    if kind not in NAMES:raise ValueError('API类型必须为image或text')
    if not isinstance(model,str) or not model.strip() or len(model)>160 or any(ord(c)<32 for c in model):raise ValueError('模型名称无效')
    secret=sys.stdin.read(8194).rstrip('\r\n') if key_stdin else getpass.getpass('请粘贴API Key（输入隐藏，回车保存）：')
    if not isinstance(secret,str) or not secret.strip():raise ValueError('API Key不能为空')
    if len(secret)>8192 or any(ord(c)<32 for c in secret):raise ValueError('API Key格式无效')
    name=NAMES[kind]
    storage=persist_user_environment(name,secret)
    return {'kind':kind,'model':model.strip(),'environment':name,'connected':True,'storage':storage}
