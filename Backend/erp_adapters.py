"""
用友 NC/U8 ERP 适配器
支持接口：
- 合同查询 (NC65: /ncchrk/perf/query)
- 发票查询 (NC65: /ncchrk/invoice/query)
- 供应商查询 (NC65: /ncchrk/supplier/query)
- 审单结果回写

参考文档：
- 用友 NC OpenAPI: https://open.yonyou.com/portal/index.html
- U8 Cloud API: https://docs.yonyoucloud.com/
"""

import os
import json
import hashlib
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

from erp_adapter import ERPAdapter


class YonyouERPAdapter(ERPAdapter):
    """用友 NC/U8 ERP 适配器"""
    
    provider_name = "yonyou"
    
    def __init__(self, user_id: Optional[str] = None):
        super().__init__(user_id)
        
        # 从环境变量读取配置
        self.base_url = os.getenv("YONYOU_BASE_URL", "https://api.yonyou.com/ncchrk")
        self.app_key = os.getenv("YONYOU_APP_KEY", "")
        self.app_secret = os.getenv("YONYOU_APP_SECRET", "")
        self.access_token = os.getenv("YONYOU_ACCESS_TOKEN", "")
        
        # 超时配置
        self.timeout = int(os.getenv("YONYOU_TIMEOUT", "10"))
        self.max_retries = int(os.getenv("YONYOU_MAX_RETRIES", "3"))
        
        # 缓存
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = int(os.getenv("YONYOU_CACHE_TTL", "300"))  # 5 分钟
    
    def _generate_sign(self, params: Dict[str, Any]) -> str:
        """生成用友 API 签名"""
        sorted_params = sorted(params.items())
        sign_str = "&".join(f"{k}={v}" for k, v in sorted_params)
        sign_str = f"{sign_str}{self.app_secret}"
        return hashlib.md5(sign_str.encode()).hexdigest().upper()
    
    def _get_access_token(self) -> str:
        """获取访问令牌（实际使用时需要实现 OAuth2 流程）"""
        if self.access_token:
            return self.access_token
        
        # 简化示例：实际应该调用 OAuth2 接口
        # token_url = f"{self.base_url}/oauth2/token"
        # response = requests.post(token_url, data={
        #     "grant_type": "client_credentials",
        #     "client_id": self.app_key,
        #     "client_secret": self.app_secret
        # })
        # token_data = response.json()
        # self.access_token = token_data["access_token"]
        
        return self.access_token or "demo_token"
    
    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict:
        """发送 HTTP 请求"""
        if not requests:
            raise ImportError("requests library is required: pip install requests")
        
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_access_token()}"
        }
        
        # 添加签名
        timestamp = str(int(time.time()))
        sign_params = {**params, "timestamp": timestamp} if params else {"timestamp": timestamp}
        sign = self._generate_sign(sign_params)
        params = params or {}
        params["sign"] = sign
        params["timestamp"] = timestamp
        
        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    params=params,
                    json=data,
                    headers=headers,
                    timeout=self.timeout
                )
                response.raise_for_status()
                result = response.json()
                
                # 用友 NC 返回格式
                if result.get("success") or result.get("code") == "200":
                    return result.get("data") or result
                else:
                    raise Exception(f"Yonyou API error: {result.get('message', 'Unknown error')}")
                    
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # 指数退避
        
        return {}
    
    def _query_contract(self, contract_no: str) -> Optional[Dict]:
        """查询合同信息"""
        try:
            # 用友 NC65 合同查询接口
            result = self._request("POST", "perf/query", data={
                "billtype": "CONTRACT",
                "filters": {
                    "contractno": contract_no
                },
                "page": {"index": 1, "size": 1}
            })
            
            if result and result.get("rows"):
                row = result["rows"][0]
                return {
                    "contract_no": row.get("contractno"),
                    "contract_name": row.get("contractname"),
                    "contract_type": row.get("contracttype"),
                    "vendor_name": row.get("vendorname"),
                    "vendor_id": row.get("vendorid"),
                    "contract_amount": float(row.get("contractamount") or 0),
                    "currency": row.get("currency", "CNY"),
                    "signed_date": row.get("signeddate"),
                    "status": row.get("status", "active"),
                    "paid_amount": float(row.get("paidamount") or 0),
                    "budget_remaining": float(row.get("budgetremaining") or 0)
                }
        except Exception as e:
            print(f"[Yonyou] Query contract failed: {e}")
        
        return None
    
    def _query_invoice(self, invoice_no: str) -> Optional[Dict]:
        """查询发票信息"""
        try:
            result = self._request("POST", "invoice/query", data={
                "filters": {
                    "invoiceno": invoice_no
                },
                "page": {"index": 1, "size": 1}
            })
            
            if result and result.get("rows"):
                row = result["rows"][0]
                return {
                    "invoice_no": row.get("invoiceno"),
                    "invoice_code": row.get("invoicecode"),
                    "invoice_date": row.get("invoicedate"),
                    "vendor_name": row.get("vendorname"),
                    "vendor_tax_no": row.get("vendortaxno"),
                    "total_amount": float(row.get("totalamount") or 0),
                    "tax_amount": float(row.get("taxamount") or 0),
                    "net_amount": float(row.get("netamount") or 0),
                    "contract_no": row.get("contractno"),
                    "status": row.get("status", "pending")
                }
        except Exception as e:
            print(f"[Yonyou] Query invoice failed: {e}")
        
        return None
    
    def _query_vendor(self, vendor_name: Optional[str] = None, vendor_id: Optional[str] = None) -> Optional[Dict]:
        """查询供应商信息"""
        try:
            filters = {}
            if vendor_id:
                filters["vendorid"] = vendor_id
            elif vendor_name:
                filters["vendorname"] = vendor_name
            
            result = self._request("POST", "supplier/query", data={
                "filters": filters,
                "page": {"index": 1, "size": 1}
            })
            
            if result and result.get("rows"):
                row = result["rows"][0]
                return {
                    "vendor_id": row.get("vendorid"),
                    "vendor_name": row.get("vendorname"),
                    "tax_no": row.get("taxno"),
                    "contact_person": row.get("contactperson"),
                    "contact_phone": row.get("contactphone"),
                    "contact_email": row.get("contactemail"),
                    "bank_name": row.get("bankname"),
                    "bank_account": row.get("bankaccount"),
                    "vendor_status": row.get("status", "active"),
                    "blacklist_hit": row.get("blacklist", False),
                    "risk_level": row.get("risklevel", "low"),
                    "rating": int(row.get("rating") or 5)
                }
        except Exception as e:
            print(f"[Yonyou] Query vendor failed: {e}")
        
        return None
    
    def fetch_context(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """获取 ERP 上下文信息"""
        contract_no = fields.get("contract_no")
        invoice_no = fields.get("invoice_no")
        vendor = fields.get("vendor") or fields.get("payee")
        
        context = {
            "provider": self.provider_name,
            "contract_amount": None,
            "po_amount": None,
            "paid_amount": None,
            "budget_remaining": None,
            "vendor_status": "unknown",
            "blacklist_hit": False,
            "expected_vendor": None,
            "invoice_exists": False,
            "existing_invoice_nos": [],
            "history_paid_amount": 0.0,
        }
        
        # 查询合同
        if contract_no:
            contract_data = self._query_contract(contract_no)
            if contract_data:
                context.update({
                    "contract_amount": contract_data.get("contract_amount"),
                    "paid_amount": contract_data.get("paid_amount"),
                    "budget_remaining": contract_data.get("budget_remaining"),
                    "expected_vendor": contract_data.get("vendor_name"),
                })
        
        # 查询发票
        if invoice_no:
            invoice_data = self._query_invoice(invoice_no)
            if invoice_data:
                context["invoice_exists"] = True
                context["existing_invoice_nos"] = [invoice_no]
                if not context.get("expected_vendor"):
                    context["expected_vendor"] = invoice_data.get("vendor_name")
        
        # 查询供应商
        if vendor or context.get("expected_vendor"):
            vendor_data = self._query_vendor(vendor_name=vendor or context["expected_vendor"])
            if vendor_data:
                context.update({
                    "vendor_status": vendor_data.get("vendor_status", "unknown"),
                    "blacklist_hit": vendor_data.get("blacklist_hit", False),
                })
        
        return context
    
    def writeback_audit_action(
        self,
        job_id: str,
        action: str,
        operator_id: str,
        result: Optional[Dict[str, Any]] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """回写审单动作到 ERP"""
        trace_id = f"YY-{datetime.now().strftime('%Y%m%d%H%M%S')}-{job_id[:8]}"
        
        try:
            # 用友 NC 审单结果回写接口（示例）
            # 实际接口需要根据用友 NC 的具体版本和配置调整
            payload = {
                "billtype": "AUDIT_RESULT",
                "data": {
                    "job_id": job_id,
                    "action": action,
                    "operator_id": operator_id,
                    "comment": comment,
                    "risk_level": (result or {}).get("risk_level"),
                    "audit_score": (result or {}).get("audit_score"),
                    "audit_time": datetime.now().isoformat()
                }
            }
            
            response_data = self._request("POST", "audit/writeback", data=payload)
            
            return {
                "trace_id": trace_id,
                "provider": self.provider_name,
                "action": action,
                "status": "synced",
                "stored": True,
                "erp_response": response_data
            }
            
        except Exception as e:
            print(f"[Yonyou] Writeback failed: {e}")
            return {
                "trace_id": trace_id,
                "provider": self.provider_name,
                "action": action,
                "status": "failed",
                "stored": False,
                "error": str(e)
            }


# 金蝶 K/3 适配器（类似实现）
class KingdeeERPAdapter(YonyouERPAdapter):
    """金蝶 K/3 Cloud ERP 适配器"""
    
    provider_name = "kingdee"
    
    def __init__(self, user_id: Optional[str] = None):
        super().__init__(user_id)
        self.base_url = os.getenv("KINGDEE_BASE_URL", "https://api.kingdee.com/K3Cloud")
        self.db_id = os.getenv("KINGDEE_DB_ID", "")
    
    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict:
        """金蝶 K/3 请求格式"""
        # 金蝶使用不同的认证和请求格式
        # 参考：https://open.kingdee.com/
        headers = {
            "Content-Type": "application/json",
            "X-KD-DBID": self.db_id
        }
        
        # 金蝶 API 调用示例
        url = f"{self.base_url}/{endpoint}"
        payload = {
            "format": "json",
            "data": data or {}
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()


# SAP ERP 适配器
class SAPERPAdapter(ERPAdapter):
    """SAP ERP 适配器（使用 RFC 或 OData）"""
    
    provider_name = "sap"
    
    def __init__(self, user_id: Optional[str] = None):
        super().__init__(user_id)
        self.base_url = os.getenv("SAP_BASE_URL", "https://api.sap.com/erp")
        self.client = os.getenv("SAP_CLIENT", "100")
        self.user = os.getenv("SAP_USER", "")
        self.password = os.getenv("SAP_PASSWORD", "")
    
    def fetch_context(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """SAP 上下文查询（示例）"""
        # SAP 查询示例：使用 BAPI 或 OData 服务
        # 合同查询：BAPI_CONTRACT_GETDETAIL
        # 供应商查询：BAPI_VENDOR_GETDETAIL
        # 发票查询：BAPI_INCOMINGINVOICE_GETDETAIL
        
        return {
            "provider": self.provider_name,
            "contract_amount": None,
            "vendor_status": "unknown",
            "blacklist_hit": False,
        }
    
    def writeback_audit_action(self, job_id: str, action: str, operator_id: str, 
                               result: Optional[Dict] = None, comment: Optional[str] = None) -> Dict:
        """SAP 审单回写"""
        # SAP BAPI 调用示例
        return {
            "trace_id": f"SAP-{job_id[:8]}",
            "provider": self.provider_name,
            "status": "queued",
            "stored": False
        }


# 工厂函数更新
def get_erp_adapter(provider: Optional[str] = None, user_id: Optional[str] = None) -> ERPAdapter:
    """获取 ERP 适配器实例"""
    resolved = (provider or os.getenv("AUDIT_ERP_PROVIDER", "mock")).strip().lower()
    
    mapping = {
        "mock": __import__("erp_adapter").SupabaseERPAdapter,
        "local": __import__("erp_adapter").SupabaseERPAdapter,
        "yonyou": YonyouERPAdapter,
        "u8": YonyouERPAdapter,
        "nc": YonyouERPAdapter,
        "kingdee": KingdeeERPAdapter,
        "k3": KingdeeERPAdapter,
        "sap": SAPERPAdapter,
    }
    
    adapter_cls = mapping.get(resolved, __import__("erp_adapter").SupabaseERPAdapter)
    return adapter_cls(user_id=user_id)


def get_supported_erp_providers() -> List[str]:
    """返回支持的 ERP 提供商列表"""
    return ["mock", "yonyou", "u8", "nc", "kingdee", "k3", "sap"]
