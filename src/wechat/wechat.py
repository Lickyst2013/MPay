#!/usr/bin/env python
# encoding: utf-8

"""
微信异步 接口封装
"""

import tornado
import time
from tornado.gen import coroutine
from tornado.ioloop import IOLoop

from .utils import (
    gen_sign, prepare_request,
    parase_xml, shake_xml, gem_radam_str
)


class WeChatPay(object):

    def __init__(self, appid, mch_id, notify_url, app_key, is_test=False):
        """
        app_id: 经过审核的appid
        mch_id: 微信支付分配的商户号
        notify_url: 回调地址
        app_key: 签名用的
        """
        self.appid = appid
        self.app_key = app_key
        self.mch_id = mch_id
        self.notify_url = notify_url
        self.is_test = is_test

    # 需要给prepaid签名
    def sign_prepaid_id(self, data):
        pay_data = {}
        pay_data["appid"] = data["appid"]
        pay_data["noncestr"] = data["nonce_str"]
        pay_data["package"] = "Sign=WXPay"
        pay_data["prepayid"] = data["prepay_id"]
        pay_data["timestamp"] = int(time.time())
        pay_data["partnerid"] = data["mch_id"]
        sign = gen_sign(pay_data, self.app_key)
        pay_data["sign"] = sign
        return pay_data

    # 统一下单
    @coroutine
    def unified_order(self, body, order_id,
                      total, user_ip, attach=None):
        """
        官方数据
           <appid>wx2421b1c4370ec43b</appid>
           <attach>支付测试</attach> 附加数据
           <body>APP支付测试</body> 商品id或描述
           <mch_id>10000100</mch_id>
           <nonce_str>1add1a30ac87aa2db72f57a2375d8fec</nonce_str>
           <notify_url>http://wxpay.weixin.qq.com/pub_v2/pay/notify.v2.php</notify_url>
           <out_trade_no>1415659990</out_trade_no>
           <spbill_create_ip>14.23.150.211</spbill_create_ip>
           <total_fee>1</total_fee>
           <trade_type>APP</trade_type>
           <sign>0CB01533B8C1EF103065174F50BCA001</sign>
        """
        data = {
            "appid": self.appid,
            "mch_id": self.mch_id,
            "body": body,
            "nonce_str": gem_radam_str(),
            "out_trade_no": order_id,
            "spbill_create_ip": user_ip,
            "trade_type": "APP",
            "total_fee": total,
            "notify_url": self.notify_url,
            "attach": attach,
        }
        sign = gen_sign(data, self.app_key)
        data["sign"] = sign
        if self.is_test:
            unified_url = "https://api.mch.weixin.qq.com/sandbox/pay/unifiedorder"
        else:
            unified_url = "https://api.mch.weixin.qq.com/pay/unifiedorder"
        # 转换成xml格式
        data = shake_xml(data)
        request = prepare_request(unified_url, data)
        # 尝试发送3次请求
        count = 3
        sleep = 3
        while True:
            try:
                count -= 1
                client = tornado.httpclient.AsyncHTTPClient()
                response = yield tornado.gen.Task(client.fetch, request)
            except tornado.httpclient.HTTPError, e:
                msg = "Failed to fetch url(%s).The reason is: %s" % (
                      unified_url, e)
                if count < 0:
                    result = (False, msg)
                    raise tornado.Return(result)
                yield tornado.gen.Task(IOLoop.instance().add_timeout,
                                       time.time() + sleep)
            else:
                """
                <xml>
                <return_code><![CDATA[SUCCESS]]></return_code>
                <return_msg><![CDATA[OK]]></return_msg>
                <appid><![CDATA[wx2421b1c4370ec43b]]></appid>
                <mch_id><![CDATA[10000100]]></mch_id>
                <nonce_str><![CDATA[IITRi8Iabbblz1Jc]]></nonce_str>
                <sign><![CDATA[7921E432F65EB8ED0CE9755F0E86D72F]]></sign>
                <result_code><![CDATA[SUCCESS]]></result_code>
                <prepay_id><![CDATA[wx201411101639507cbf6ffd8b0779950874]]></prepay_id>
                <trade_type><![CDATA[APP]]></trade_type>
                </xml>
                """
                if response and not response.error:
                    body = response.body
                    data = parase_xml(body)
                    if data["return_code"] == "SUCCESS" and data["result_code"] == "SUCCESS":
                        pay_data = self.sign_prepaid_id(data)
                        data["pay_data"] = pay_data
                        result = (True, data)
                        raise tornado.gen.Return(result)
                    else:
                        # take a log
                        pass
                    result = (False, data)
                    raise tornado.gen.Return(result)
                else:
                    result = (False, "error")
                    raise tornado.gen.Return(result)

    # 查询订单
    @coroutine
    def query_order(self, weixin_id=None, order_id=None):
        """
        transaction_id: 微信的订单号
        out_trade_no: 商家id
        规则：二选一, 优先微信id
        """
        data = {
            "appid": self.appid,
            "mch_id": self.mch_id,
            "nonce_str": gem_radam_str(),
            # "transaction_id": weixin_id,
            # "out_trade_no": order_id,
        }
        if weixin_id:
            data["transaction_id"] = weixin_id
        if order_id and not weixin_id:
            data["out_trade_no"] = order_id
        sign = gen_sign(data, self.app_key)
        data["sign"] = sign
        if self.is_test:
            query_url = "https://api.mch.weixin.qq.com/sandbox/pay/orderquery"
        else:
            query_url = "https://api.mch.weixin.qq.com/pay/orderquery"
        requst_data = shake_xml(data)
        request = prepare_request(query_url, requst_data)
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
                    raise tornado.gen.Return()
                yield tornado.gen.Task(IOLoop.instance().add_timeout,
                                       time.time() + sleep)
            else:
                if response and not response.error:
                    body = response.body
                    data = parase_xml(body)
                    if data["return_code"] == "SUCCESS" and data["result_code"] == "SUCCESS" :
                        # trade_state为交易状态
                        if data["trade_state"] == "SUCCESS":
                            result = (True, data)
                            raise tornado.gen.Return(result)
                        else:
                            result = (False, data)
                            raise tornado.gen.Return(result)

                    else:
                        result = (False, data)
                        raise tornado.gen.Return(result)
                else:
                    result = (False, response.error)
                    raise tornado.gen.Return(result)
