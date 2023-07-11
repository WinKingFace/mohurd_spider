# -*- coding: utf-8 -*-
# @Time    : 2023/7/11 3:10 下午
# @Author  : CC
import functools
import json
import os
import re

import requests
from Crypto.Cipher import AES


def extract_first_json(s):
    rightmost_brace_index = s.rfind('}')
    if rightmost_brace_index != -1:
        substring = s[:rightmost_brace_index + 1]
        json_object = json.loads(substring)
        return json_object
    else:
        return {}


def check_token(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        for _ in range(2):  # 最多尝试2次
            result = func(self, *args, **kwargs)
            if 'token失效' not in result:  # 如果token有效
                return result  # 返回结果
            # 如果token失效
            if os.path.exists('token.txt'):  # 检查token.txt文件是否存在
                os.remove('token.txt')  # 删除token.txt文件
            self.generate_accesstoken.cache_clear()  # 清除generate_accesstoken的缓存
        raise Exception("Token失效，已尝试重新生成但未能解决问题")

    return wrapper


class Mohurd:
    def __init__(self, params):
        self.api_url = 'https://jzsc.mohurd.gov.cn/APi/webApi/dataservice/query/comp/list'
        self.token_url = "https://jzsc.mohurd.gov.cn/APi/webApi/geetest/startCaptcha"
        self.s = requests.session()
        self.key = 'jo8j9wGw%6HbxfFn'.encode()
        self.iv = '0123456789ABCDEF'.encode()
        self.params = params
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36',
            'Referer': 'https://jzsc.mohurd.gov.cn/data/company'
        }

    def req_mohurd(self):
        response = self.s.get(self.api_url, params=self.params, headers=self.headers)
        return response.text

    def parse_mohurd(self, data):
        text = bytes.fromhex(data)
        aes = AES.new(self.key, AES.MODE_CBC, self.iv)
        plain_text = aes.decrypt(text).decode()
        return plain_text

    def crawl_mohurd(self):
        """:arg
        QY_FR_NAME: 企业法定代表人
        QY_NAME: 企业名称
        QY_REGION_NAME: 企业注册属地
        QY_ORG_CODE: 统一社会信用代码
        """
        data = self.req_mohurd()
        plain_text = self.parse_mohurd(data)
        json_data = extract_first_json(plain_text)

        return json_data.get("data").get("list")

    def generate_accesstoken(self):
        if os.path.exists('token.txt'):  # 检查token.txt文件是否存在
            with open('token.txt', 'r') as f:
                access_token = f.read().strip()
        else:
            data = self.parse_mohurd(self.start())
            challenge_pattern = r'"challenge":"(.*?)"'
            gt_pattern = r'"gt":"(.*?)"'
            randomId_pattern = r'"randomId":"(.*?)"'

            challenge = re.search(challenge_pattern, data)
            gt = re.search(gt_pattern, data)
            rid = re.search(randomId_pattern, data)

            if challenge and gt:
                r_data = self.get_token()
                r_challenge = r_data.get("challenge")
                r_validate = r_data.get("validate")
                access_token = self.verifyLoginCode(rid.group(1), r_challenge, r_validate)
            else:
                raise Exception('Failed to generate Accesstoken.')
            # 将新生成的access token写入到token.txt文件中
            with open('token.txt', 'w') as f:
                f.write(access_token)

        return access_token

    def start(self):
        response = self.s.get(self.token_url, headers=self.headers)
        return response.text

    def verifyLoginCode(self, randomId, challenge, validate):
        url = "https://jzsc.mohurd.gov.cn/APi/webApi/geetest/verifyLoginCode"
        params = {
            'geetest_challenge': challenge,
            'geetest_validate': validate,
            'geetest_seccode': f"{validate}|jordan",
            'randomId': randomId,
        }
        response = self.s.get(url, params=params, headers=self.headers)
        text = self.parse_mohurd(response.text)
        json_text = json.loads(text)
        return json_text.get("data", {}).get("accessToken")

    def save_to_file(self, data, folder_name, file_name):
        if "token失效" in data:
            return
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)
        with open(f"{folder_name}/{file_name}", 'w') as f:
            f.write(str(extract_first_json(data)))

    def get_data_from_file(self, file_path):
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                try:
                    return eval(f.read())
                except json.JSONDecodeError:
                    print(f"Error: File {file_path} does not contain valid JSON.")
        return None

    @check_token
    def reg_staff_list_mohurd(self, qyId):
        folder = "注册人员"
        data_folder = os.path.join(os.getcwd(), folder)
        file_path = f'{data_folder}/{qyId}.txt'
        data = self.get_data_from_file(file_path)
        if data is not None:
            print("注册人员（从文件读取）", data)
            return data
        headers = self.headers.copy()
        headers["Accesstoken"] = self.generate_accesstoken()
        url = f"https://jzsc.mohurd.gov.cn/APi/webApi/dataservice/query/comp/regStaffList"
        params = {
            'qyId': qyId,
            'pg': 0,
            'pgsz': 15,
        }
        response = self.s.get(url, params=params, headers=headers)
        plain_text = self.parse_mohurd(response.text)
        print(f"{folder}（从网络获取）", plain_text)
        self.save_to_file(plain_text, data_folder, f'{qyId}.txt')
        return extract_first_json(plain_text)


if __name__ == "__main__":
    params = {
        'pg': 0,
        'pgsz': 15,
        'total': 459
    }

    mohurd = Mohurd(params)
    companies = mohurd.crawl_mohurd()
    for company in companies:
        qyId = company.get('QY_ID')
        com_reg_staff_resp = mohurd.reg_staff_list_mohurd(qyId)
