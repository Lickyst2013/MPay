#!/usr/bin/env python
# encoding: utf-8

import base64
import hashlib
import time
import tornado
from tornado.gen import coroutine
from tornado.ioloop import IOLoop
from OpenSSL import crypto
from urllib import urlencode
import urllib

from exception import CertificationError


# 准备request
def prepare_request(url, data):
    request = tornado.httpclient.HTTPRequest(
        url,
        method="POST",
        body=data,
        headers={'content-type': 'application/x-www-form-urlencoded'},
        # validate_cert=True)
        validate_cert=False)
    return request


class UnionPay(object):

    def __init__(self, merId, backUrl, pri_key,
                 pub_key, password, is_test):
        """
        从上到下参数是:
        merId:  商户id
        backUrl: 后台url,用于回调
        pri_key: 私钥
        pub_key: 公钥
        password: 证书密码
        is_test: 是否test 环境
        """
        self.merId = merId
        self.backUrl = backUrl
        self.is_test = is_test
        self.pub_key = pub_key
        self.password = password
        self.load_pri_key(pri_key)

    def load_pri_key(self, pri_key):
        pfile = open(pri_key, 'rb').read()
        self.pkcs = crypto.load_pkcs12(pfile, self.password)
        self.cert_id = str(self.pkcs.get_certificate().get_serial_number())
        self.pri_key = self.pkcs.get_privatekey()

    # 生成签名
    def sign_data(self, data):
        message = self.make_digest(data)
        # pkey = open(self.pri_key).read()
        # pri_key = crypto.load_privatekey(crypto.FILETYPE_PEM, pkey)
        signature = crypto.sign(self.pri_key, message, "sha1")
        sign = base64.b64encode(signature)
        return sign

    def make_digest(self, data):
        """
        生成签名hash值
        """
        sign_list = []
        for key in sorted(data.keys()):
            if data[key]:
                sign_list.append("%s=%s" % (key, unicode(data[key])))
        sign_string = "&".join(sign_list)
        if isinstance(sign_string, unicode):
            sign_string = sign_string.encode("utf-8")
        digest = hashlib.sha1(sign_string).hexdigest().lower()
        return digest

    # 验证签名
    def verify_sign(self, data):
        signature = data.pop('signature')
        signature = urllib.unquote(signature)
        signature = signature.replace(' ', '+')
        signature = base64.b64decode(signature)
        raw_data = self.make_digest(data)
        pkey = open(self.pub_key, "rb").read()
        pub_key = crypto.load_certificate(crypto.FILETYPE_PEM, pkey)
        try:
            crypto.verify(pub_key, signature, raw_data, "sha1")
        except Exception:
            raise CertificationError("certfity not valid!")
        return True

    # 获取银联流水号, 预支付接口
    @coroutine
    def prepay_order(self, **kwargs):
        """
        具体参数查看接口 https://open.unionpay.com/ajweb/product/detail?id=3
        """
        data = {}
        pay_keys = ["orderId", "txnAmt", "txnTime"]
        for key in pay_keys:
            data[key] = kwargs[key]
        if kwargs.get("extra", None):
            data["reqReserved"] = kwargs["extra"]

        # 请求支付固定数据
        data["version"] = "5.0.0"
        data["encoding"] = "UTF-8"
        data["signMethod"] = "01"
        data["txnType"] = "01"
        data["txnSubType"] = "01"
        # 产品类型 000201:b2c
        data["bizType"] = "000201"
        data["channelType"] = "08"
        # 接入类型 0：普通商户直连接入 1：收单机构接入
        data["accessType"] = "0"
        data["merId"] = self.merId
        data["currencyCode"] = "156"
        data["backUrl"] = self.backUrl
        data["certId"] = self.cert_id
        sign = self.sign_data(data)
        signature = urlencode({'signature': sign})[10:]
        data["signature"] = signature
        if self.is_test:
            pay_url = "https://101.231.204.80:5000/gateway/api/appTransReq.do"
        else:
            pay_url = "https://gateway.95516.com/gateway/api/appTransReq.do"
        request_data = self.to_form_string(data)
        request = prepare_request(pay_url, request_data)

        # 发送3次请求，中间间隔3秒
        count = 3
        sleep = 3
        while True:
            try:
                count -= 1
                client = tornado.httpclient.AsyncHTTPClient()
                response = yield tornado.gen.Task(client.fetch, request)
            except tornado.httpclient.HTTPError, e:
                msg = "Failed to fetch url(%s).The reason is: %s" % (
                      pay_url, e)
                if count < 0:
                    result = (False, {"respMsg": msg})
                    raise tornado.gen.Return(result)
                yield tornado.gen.Task(IOLoop.instance().add_timeout,
                                       time.time() + sleep)
            else:
                if response and not response.error:
                    res_data = self.to_dict(response.body)
                    result = (True, res_data)
                    raise tornado.gen.Return(result)
                else:
                    result = (False, {"respMsg": response.error})
                    raise tornado.gen.Return(result)

    # 验单接口
    @coroutine
    def query_order(self, orderId=None, txnTime=None):
        """
        """
        data = {}
        # 请求支付固定数据
        data["version"] = "5.0.0"
        data["encoding"] = "UTF-8"
        data["certId"] = self.cert_id
        data["signMethod"] = "01"
        data["txnType"] = "00"
        data["txnSubType"] = "00"
        data["bizType"] = "000000"
        # 接入类型 0：普通商户直连接入 1：收单机构接入
        data["accessType"] = "0"
        data["merId"] = self.merId
        data["orderId"] = orderId
        data["txnTime"] = txnTime
        sign = self.sign_data(data)
        signature = urlencode({'signature': sign})[10:]
        data["signature"] = signature
        if self.is_test:
            query_url = "https://101.231.204.80:5000/gateway/api/queryTrans.do"
        else:
            query_url = "https://gateway.95516.com/gateway/api/queryTrans.do"
        request_data = self.to_form_string(data)
        request = prepare_request(query_url, request_data)
        count = 3
        sleep = 3
        while True:
            try:
                count -= 1
                client = tornado.httpclient.AsyncHTTPClient()
                response = yield tornado.gen.Task(client.fetch, request)
            except tornado.httpclient.HTTPError, e:
                msg = "Failed to fetch url(%s).The reason is: %s" % (
                      query_url, e)
                if count < 0:
                    result = (False, msg)
                    raise tornado.gen.Return(result)
                yield tornado.gen.Task(IOLoop.instance().add_timeout,
                                       time.time() + sleep)
            else:
                if response and not response.error:
                    res_data = self.to_dict(response.body)
                    result = (True, res_data)
                    raise tornado.gen.Return(result)
                else:
                    result = (False, response.error)
                    raise tornado.gen.Return(result)

    def to_dict(self, req_string):
        data = {}
        for raw_str in req_string.split("&"):
            key, value = raw_str.split("=", 1)
            data[key] = value
        return data

    def to_form_string(self, data):
        sign_list = []
        for key in sorted(data.keys()):
            if not isinstance(data[key], dict):
                sign_list.append("%s=%s" % (key, unicode(data[key])))
        result = "&".join(sign_list)
        return result
