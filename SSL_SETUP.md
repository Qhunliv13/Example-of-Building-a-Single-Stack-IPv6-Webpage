# SSL 证书配置方法 (Let's Encrypt DNS-01)

使用 Let's Encrypt 的 DNS-01 挑战申请证书，无需公网 HTTP 访问。只需 DNS 管理 API 权限。

---

## 原理

```
1. ACME 客户端 → Let's Encrypt CA：请求为 example.com 签发证书
2. Let's Encrypt CA → ACME 客户端：请证明你拥有 example.com 的 DNS 控制权
   挑战方式：在 _acme-challenge.example.com 创建一条 TXT 记录，内容为指定的验证令牌
3. ACME 客户端 → DNS API：创建 TXT 记录
4. ACME 客户端 → Let's Encrypt CA：验证请求已就绪
5. Let's Encrypt CA → DNS：查询 _acme-challenge.example.com 的 TXT 记录
6. 匹配成功 → 签发证书
```

DNS-01 的优势：不需要公网 IP、不需要 80/443 端口开放、不依赖 HTTP 可达性。纯 IPv6 或内网环境均可使用。

---

## 前置条件

- Python 3.8+
- 已安装 `pip install certbot acme cryptography josepy requests`
- 有 DNS 管理 API 权限（Cloudflare / 阿里云 / DNSPod 等）
- Let's Encrypt 速率限制：每域名每周最多 5 张证书

---

## 以 Cloudflare 为例

### 1. 准备 API Token

Cloudflare 后台 → 我的资料 → API 令牌 → 创建令牌 → 自定义令牌

权限要求：
- 区域 → DNS → 编辑
- 区域资源 → 包含所有区域

### 2. 获取 Zone ID

域名概览页面 → 右侧底部 → 账户 ID（即 Zone ID）

### 3. ACME 脚本

```python
import urllib.request, json, time
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from acme import client, messages, challenges
from acme.client import ClientNetwork
from acme.messages import Directory
import josepy as jose

DOMAIN = "yourdomain.com"
EMAIL = "admin@yourdomain.com"
CF_TOKEN = "your_cloudflare_api_token"
CF_ZONE = "your_cloudflare_zone_id"
CERT_DIR = "/etc/letsencrypt/live/yourdomain.com"

# 生成账户密钥
key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
jwkey = jose.JWKRSA(key=key)
net = ClientNetwork(key=jwkey, user_agent="acme-client")

# 获取 ACME 目录
dir_data = json.load(urllib.request.urlopen("https://acme-v02.api.letsencrypt.org/directory"))
directory = Directory(dir_data)
acme_cli = client.ClientV2(directory, net)

# 注册账户
reg = acme_cli.new_account(messages.NewRegistration.from_data(email=EMAIL, terms_of_service_agreed=True))

# 生成域名密钥和 CSR
dom_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
csr = x509.CertificateSigningRequestBuilder().subject_name(
    x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, DOMAIN)])
).add_extension(
    x509.SubjectAlternativeName([x509.DNSName(DOMAIN)]), critical=False
).sign(dom_key, hashes.SHA256(), backend=default_backend())
csr_pem = csr.public_bytes(serialization.Encoding.PEM)

# 提交订单
order = acme_cli.new_order(csr_pem)

# 处理 DNS-01 挑战
for auth in order.authorizations:
    for chall_body in auth.body.challenges:
        if isinstance(chall_body.chall, challenges.DNS01):
            validation = chall_body.chall.validation(jwkey)
            record_name = f"_acme-challenge.{DOMAIN}"

            # 通过 Cloudflare API 创建 TXT 记录
            headers = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}

            # 删除旧记录
            resp = requests.get(
                f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE}/dns_records"
                f"?type=TXT&name={record_name}", headers=headers)
            for r in resp.json().get("result", []):
                requests.delete(
                    f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE}/dns_records/{r['id']}",
                    headers=headers)

            # 创建新记录
            requests.post(f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE}/dns_records",
                headers=headers,
                json={"type":"TXT","name":record_name,"content":f'"{validation}"',"ttl":120})

            time.sleep(30)  # 等待 DNS 传播

            # 通知 Let's Encrypt 验证
            acme_cli.answer_challenge(chall_body, chall_body.chall.response(jwkey))
            time.sleep(10)

            # 获取证书
            order = acme_cli.poll_and_finalize(order)

            # 保存证书和密钥
            import os
            os.makedirs(CERT_DIR, exist_ok=True)
            with open(os.path.join(CERT_DIR, "fullchain.pem"), "w") as f:
                f.write(order.fullchain_pem)
            with open(os.path.join(CERT_DIR, "privkey.pem"), "wb") as f:
                f.write(dom_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()))
```

### 4. Nginx 配置

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;
    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;

    location / {
        # ...
    }
}
```

---

## 其他 DNS 服务商

### 阿里云 DNS（Aliyun）

```python
# pip install aliyun-python-sdk-core aliyun-python-sdk-domain
from aliyunsdkcore.client import AcsClient
from aliyunsdkalidns.request.v20150109 import AddDomainRecordRequest, DeleteDomainRecordRequest

client = AcsClient("access_key_id", "access_key_secret", "cn-hangzhou")

# 添加 TXT 记录
req = AddDomainRecordRequest.AddDomainRecordRequest()
req.set_DomainName("yourdomain.com")
req.set_RR("_acme-challenge")
req.set_Type("TXT")
req.set_Value(validation_token)
req.set_TTL(120)
client.do_action_with_exception(req)
```

### DNSPod（腾讯云）

```python
# pip install tencentcloud-sdk-python
from tencentcloud.common import credential
from tencentcloud.dnspod.v20210323 import dnspod_client, models

cred = credential.Credential("secret_id", "secret_key")
client = dnspod_client.DnspodClient(cred, "")

req = models.CreateRecordRequest()
req.Domain = "yourdomain.com"
req.SubDomain = "_acme-challenge"
req.RecordType = "TXT"
req.Value = validation_token
req.RecordLine = "默认"
client.CreateRecord(req)
```

---

## 证书自动续期

Let's Encrypt 证书有效期为 90 天。可用系统定时任务（cron / Windows Task Scheduler）每月执行一次 ACME 脚本。

```bash
# Linux cron (每月1日执行)
0 0 1 * * python /path/to/acme_script.py

# Windows 计划任务
schtasks /create /tn "RenewSSL" /tr "python C:\path\to\acme_script.py" /sc monthly /d 1
```

---

## 常见问题

**Q: 速率限制（rateLimited）**
A: 每域名每周最多 5 张证书。调试过多时会触发。等待 1 小时后再试。

**Q: DNS 传播超时**
A: 不同 DNS 服务商传播速度不同。Cloudflare 约 10-30 秒，阿里云可能需要 60 秒以上。将脚本中的 `time.sleep(30)` 适当延长。

**Q: 403 Forbidden**
A: API Token 权限不足。确认 Token 有 DNS 编辑权限，且关联了正确的域名。

**Q: TLS 握手失败**
A: nginx 配置文件中的 cert 路径错误，或证书文件权限不对。确认路径和文件可读。
