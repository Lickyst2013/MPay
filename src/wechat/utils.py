#!/usr/bin/env python
# encoding: utf-8

import tornado

import xml.etree.ElementTree as ET
import hashlib
import string
from random import *


# 生成签名
def gen_sign(data, app_key):
    if not isinstance(data, dict):
        raise Exception("data must be dict type!")
    sign_list = []
    for key in sorted(data.keys()):
        if data[key]:
            sign_list.append("%s=%s" % (key, unicode(data[key])))
    strings = "&".join(sign_list) + '&key=%s'
    sign_string = strings % app_key
    if isinstance(sign_string, unicode):
        sign_string = sign_string.encode("utf-8")
    sign = hashlib.md5(sign_string).hexdigest().upper()
    return sign


# 准备request
def prepare_request(url, data):
    # header = {'Content-Type': 'application/atom+xml'},
    request = tornado.httpclient.HTTPRequest(
        url,
        method="POST",
        body=data,
        # connect_timeout=10, #user default
        # request_timeout=10,
        # headers=header,
        validate_cert=True)
    return request


# change xml to dict
def parase_xml(data):
    tree = ET.fromstring(data)
    elements = [(key.tag, key.text) for key in tree]
    result = dict(elements)
    return result


# change dict to xml
def shake_xml(data):
    root = ET.Element('xml')
    for key, value in data.items():
        if not value:
            continue
        element = ET.SubElement(root, key)
        element.text = unicode(value)
    result = ET.tostring(root)
    return result


# 返回随机数
def gem_radam_str(length=26):
    characters = string.ascii_letters + string.digits
    radom_str = "".join(choice(characters) for x in range(randint(20, length)))
    return radom_str
