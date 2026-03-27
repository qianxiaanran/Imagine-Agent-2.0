# 阿里云短信认证客户端
import json
from typing import Optional

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.acs_exception.exceptions import ClientException, ServerException
from aliyunsdkdypnsapi.request.v20170525.SendSmsVerifyCodeRequest import SendSmsVerifyCodeRequest
from aliyunsdkdypnsapi.request.v20170525.CheckSmsVerifyCodeRequest import CheckSmsVerifyCodeRequest

from app_settings import ALIYUN_ACCESS_KEY_ID, ALIYUN_ACCESS_KEY_SECRET

"""
只使用【号码认证-短信认证服务】来发送 & 校验验证码，不再走短信服务(SMS)。

注意：
1. SignName 和 TemplateCode 要用「短信认证服务 > 短信认证参数配置」里的赠送签名/模板，
   比如 登录/注册模板 TemplateCode=100001。
2. 本文件里 ACCESS_KEY 建议从环境变量读取，别写死真实密钥。
"""

ACCESS_KEY_ID = ALIYUN_ACCESS_KEY_ID
ACCESS_KEY_SECRET = ALIYUN_ACCESS_KEY_SECRET

REGION_ID = "cn-hangzhou"  # 号码认证服务所在地域就是杭州

# 这里填你「赠送签名配置」里的签名名称（必须一模一样）
SIGN_NAME = "速通互联验证平台"

# 这里填你「赠送模板配置」里的模板 CODE，比如 登录/注册模板=100001
TEMPLATE_CODE = "100001"

# 如果你在短信认证控制台里创建了“方案名”，这里填同一个名称；没有就保持 None
SCHEME_NAME: Optional[str] = None

# 验证码有效期（分钟），和模板里的 ${min} 对应
VERIFY_MINUTES = 5

# 创建 client
_client: Optional[AcsClient] = None


def _get_client() -> AcsClient:
    global _client
    if _client is None:
        if not ACCESS_KEY_ID or not ACCESS_KEY_SECRET:
            raise RuntimeError("请先在环境变量中配置 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET")
        _client = AcsClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, REGION_ID)
    return _client


def send_login_code(phone: str) -> bool:
    """
    使用短信认证服务发送登录/注册验证码。
    验证码由阿里云生成和管理，我们只负责触发发送。
    """
    client = _get_client()

    request = SendSmsVerifyCodeRequest()
    request.set_accept_format("JSON")

    # 基本参数
    request.set_PhoneNumber(phone)
    request.set_SignName(SIGN_NAME)
    request.set_TemplateCode(TEMPLATE_CODE)

    # 模板变量：让阿里云自动生成验证码，用 ##code## 占位
    # 模板内容示例：您的验证码为${code}，${min}分钟内有效...
    template_param = {
        "code": "##code##",
        "min": str(VERIFY_MINUTES),
    }
    request.set_TemplateParam(json.dumps(template_param, ensure_ascii=False))


    # 如果控制台里有“方案名”，这里要保持一致
    if SCHEME_NAME:
        request.set_SchemeName(SCHEME_NAME)

    try:
        response_str = client.do_action_with_exception(request)
        resp = json.loads(response_str.decode("utf-8"))
        print("[SendSmsVerifyCode Response]", resp)

        if resp.get("Code") != "OK":
            # 这里可以根据不同错误 Code 做更细的提示
            print("[Aliyun SmsAuth] send_login_code failed:", resp.get("Message"))
            return False

        return True

    except (ClientException, ServerException) as e:
        print("[Aliyun SmsAuth Error] send_login_code:", e)
        return False


def verify_login_code(phone: str, code: str) -> bool:
    """
    使用短信认证服务校验验证码。
    :return: True=验证通过，False=验证码错误或过期等
    """
    client = _get_client()

    request = CheckSmsVerifyCodeRequest()
    request.set_accept_format("JSON")

    request.set_PhoneNumber(phone)
    request.set_VerifyCode(code.strip())

    if SCHEME_NAME:
        request.set_SchemeName(SCHEME_NAME)

    try:
        resp_str = client.do_action_with_exception(request)
        resp = json.loads(resp_str.decode("utf-8"))
        print("[CheckSmsVerifyCode Response]", resp)

        # 接口本身调用成功
        if resp.get("Code") != "OK":
            print("[Aliyun SmsAuth] verify_login_code api failed:", resp.get("Message"))
            return False

        # 真正的校验结果在 Model.VerifyResult 里
        model = resp.get("Model") or {}
        return model.get("VerifyResult") == "PASS"

    except (ClientException, ServerException) as e:
        print("[Aliyun SmsAuth Error] verify_login_code:", e)
        return False
