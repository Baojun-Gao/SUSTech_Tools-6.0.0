#!/usr/bin/env python3    # -*- coding: utf-8 -*

"""
main.py 南科大TIS喵课助手

@CreateDate 2021-1-9
@UpdateDate 2026-9-4
"""

import _thread
import time
import os
from getpass import getpass
from json import loads, dumps
from re import findall

import requests
from colorama import init

import sys
import warnings
from urllib3.exceptions import InsecureRequestWarning


def warn(message, category, filename, lineno, _file=None, line=None):
    if category is not InsecureRequestWarning:
        sys.stderr.write(warnings.formatwarning(message, category, filename, lineno, line))


CLASS_CACHE_PATH = "class.txt"
COURSE_INFO_PATH = "course.txt"
warnings.showwarning = warn
SUCCESS = "[\x1b[0;32m+\x1b[0m] "
STAR = "[\x1b[0;32m*\x1b[0m] "
ERROR = "[\x1b[0;31mx\x1b[0m] "
INFO = "[\x1b[0;36m!\x1b[0m] "
FAIL = "[\x1b[0;33m-\x1b[0m] "
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
head = {
    "user-agent": UA,
    "x-requested-with": "XMLHttpRequest"
}

COURSE_TYPE = {'bxxk': "通识必修选课", 'xxxk': "通识选修选课", "kzyxk": '培养方案内课程',
               "zynknjxk": '非培养方案内课程', "jhnxk": '计划内选课新生'}

course_list = []  # 需要喵的课程队列
# 由于Tis的新限制，逻辑改为同时只选一门课


def load_course():
    """ 用于加载本地要喵的课程
    如果存在文件就读文件里的，不存在就手动录入
    有些(我忘了是哪些了)情况会在文件头会有几个不可见字符，但是会被python读进来，所以第一行建议忽略留空"""
    courses = []
    if os.path.exists(CLASS_CACHE_PATH) and os.path.isfile(CLASS_CACHE_PATH):
        print(INFO + "读取规划课表...")
        with open(CLASS_CACHE_PATH, "r", encoding="utf8") as f:
            courses = f.readlines()
        print(SUCCESS + "规划课表读取完毕")
    else:
        print(FAIL + "没有找到规划课表，请手动输入课程信息，输入-1结束录入")
        s = "===本文件是待喵课程的列表，一行输入一个课程名字==请勿删除本行==="
        while s != "-1":
            courses.append(s)
            s = input()
        s = input(INFO + "是否保存录入的信息（y/N）？")
        if s in "yY":
            with open(CLASS_CACHE_PATH, "w", encoding="utf8") as f:
                f.writelines('\n'.join(courses))
    return courses


def cas_login(sid, pwd):
    import re
    print(INFO + "测试CAS链接...")
    login_url = "https://cas.sustech.edu.cn/cas/login?service=https%3A%2F%2Ftis.sustech.edu.cn%2Fcas"
    session = requests.Session()

    # 设置完整的浏览器请求头（模拟真实浏览器）
    session.headers.update({
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })

    try:
        # 1. 获取登录页面（提取所有隐藏字段）
        resp = session.get(login_url, verify=False)
        resp.raise_for_status()
        print(SUCCESS + "成功连接到CAS...")
        html = resp.text

        # 提取 execution（必填）
        exec_match = re.search(r'name="execution"\s+value="([^"]+)"', html)
        if not exec_match:
            print(ERROR + "未找到 execution 字段，登录页面结构可能已变化")
            return None
        execution = exec_match.group(1)

        # 提取 lt（可选）
        lt_match = re.search(r'name="lt"\s+value="([^"]+)"', html)
        lt = lt_match.group(1) if lt_match else ''

        # 提取 service（可选，但通常与 URL 中一致）
        service_match = re.search(r'name="service"\s+value="([^"]+)"', html)
        service = service_match.group(1) if service_match else 'https://tis.sustech.edu.cn/cas'

        # 构建登录数据
        data = {
            'username': sid,
            'password': pwd,
            'execution': execution,
            '_eventId': 'submit',
        }
        if lt:
            data['lt'] = lt
        if service:
            data['service'] = service

        # 打印调试信息（隐藏密码）
        debug_data = data.copy()
        debug_data['password'] = '******'
        print("[DEBUG] 提交数据:", debug_data)

        # 2. 提交登录（添加 Referer 和 Content-Type）
        print(INFO + "登录中...")
        # 更新 headers，添加 Referer 和 Content-Type
        session.headers.update({
            'Referer': login_url,
            'Content-Type': 'application/x-www-form-urlencoded',
        })
        resp = session.post(login_url, data=data, allow_redirects=True, verify=False)

        # 3. 检查是否成功（跳转到 tis）
        if resp.url.startswith("https://tis.sustech.edu.cn"):
            print(SUCCESS + "登录成功")
            return session
        else:
            # 如果未跳转，保存响应以便分析
            with open("login_failed.html", "w", encoding="utf-8") as f:
                f.write(resp.text)
            print(ERROR + "登录失败，响应已保存为 login_failed.html")
            # 尝试从响应中提取错误提示
            error_match = re.search(r'<div[^>]*class="errors"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
            if error_match:
                print("[DEBUG] 错误信息:", error_match.group(1).strip())
            else:
                # 提取页面标题
                title_match = re.search(r'<title>(.*?)</title>', resp.text)
                title = title_match.group(1) if title_match else "无标题"
                print("[DEBUG] 响应页面标题:", title)
            return None

    except Exception as ex:
        print(ERROR + f"CAS登录异常: {ex}")
        return None

def getinfo(semester_data, session):
    """ 用于向tis请求当前学期的课程ID，得到的ID将用于选课的请求
    输入当前学期的日期信息，返回的json包括了课程名和内部的ID """
    if os.path.exists(COURSE_INFO_PATH) and os.path.isfile(COURSE_INFO_PATH):
        print(INFO + f"读取本地缓存的课程信息，如果需要更新请删除{COURSE_INFO_PATH}文件")
        with open(COURSE_INFO_PATH, "r", encoding="utf8") as f:
            cached_course_list = f.readlines()
        try:
            cached_time = cached_course_list[0].strip()
            if cached_time == semester_data['p_xnxq']:
                _course_info = loads(cached_course_list[1])
                print(SUCCESS + f"课程信息读取完毕，共读取{str(len(_course_info))}门课程信息\n")
                return _course_info
            else:
                print(INFO + "缓存文件已过期，重新获取课程信息")
        except Exception as ex:
            print(ERROR + f"缓存文件损坏，重新获取课程信息，{ex}")
    print(INFO + "从服务器下载课程信息，请稍等...")
    _course_info = {}
    for c_type in COURSE_TYPE.keys():
        data = {
            "p_xn": semester_data['p_xn'],  # 当前学年
            "p_xq": semester_data['p_xq'],  # 当前学期
            "p_xnxq": semester_data['p_xnxq'],  # 当前学年学期
            "p_pylx": 1,
            "mxpylx": 1,
            "p_xkfsdm": c_type,
            "pageNum": 1,
            "pageSize": 1000  # 每学期总共开课在1000左右，所以单分类可以包括学期的全部课程
        }
        print("[\x1b[0;36m*\x1b[0m] " + f"获取 {COURSE_TYPE[c_type]} 列表...")
        req = session.post('https://tis.sustech.edu.cn/Xsxk/queryKxrw', data=data, headers=head, verify=False)
        raw_class_data = loads(req.text)
        if raw_class_data.get('kxrwList'):
            for i in raw_class_data['kxrwList']['list']:
                _course_info[i['rwmc']] = (i['id'], c_type)
    print(SUCCESS + f"课程信息读取完毕，共读取{str(len(_course_info))}门课程信息")
    s = input(INFO + "是否保存读取的课程信息（y/N）？")
    if s in "yY":
        with open(COURSE_INFO_PATH, "w", encoding="utf8") as f:
            f.write(str(semester_data['p_xnxq']) + "\n")
            f.write(dumps(_course_info))
    return _course_info


def submit(semester_data, session, loop=3):
    """ 用于向tis发送喵课的请求
    这里假设主要耗时在网络IO上，本地处理时间几乎可以忽略
    （什么，购物车是怎么回事？那首先排除教务系统是个魔改的电商项目）"""
    for _ in range(loop):
        if not course_list:
            print(SUCCESS + "⌯'ㅅ'⌯所有课程已喵完，再见😾")
            exec("os._exit(0)")  # lint hack
        c_id, c_type, c_name = course_list[0]
        data = {
            "p_pylx": 1,
            "p_xktjz": "rwtjzyx",  # 提交至，可选任务，rwtjzgwc提交至购物车，rwtjzyx提交至已选 gwctjzyx购物车提交至已选
            "p_xn": semester_data['p_xn'],
            "p_xq": semester_data['p_xq'],
            "p_xnxq": semester_data['p_xnxq'],
            "p_xkfsdm": c_type,  # 选课方式
            "p_id": c_id,  # 课程id
            "p_sfxsgwckb": 1,  # 固定
        }
        req = session.post('https://tis.sustech.edu.cn/Xsxk/addGouwuche', data=data, headers=head, verify=False)
        res = loads(req.text)['message']
        if "成功" in req.text:
            print("[\x1b[0;34m{}\x1b[0m]".format("=" * 50), flush=True)
            print("[\x1b[0;34m█\x1b[0m]\t\t\t" + res, flush=True)
            print("[\x1b[0;34m{}\x1b[0m]".format("=" * 50), flush=True)
            course_list.pop(0)
        else:
            print("[\x1b[0;30m-\x1b[0m]\t\t\t" + res, flush=True)
        if any(map(lambda x: x in req.text, ["冲突", "已选", "已满"])):
            print(f"[\x1b[0;31m!\x1b[0m] ({c_name})因为({res})跳过", flush=True)
            course_list.pop(0)
        time.sleep(1)


if __name__ == '__main__':
    init(autoreset=True)  # 某窗口系统的优质终端并不直接支持如下转义彩色字符，所以需要一些库来帮忙
    course_name_list = load_course()  # 读取本地待喵的课程
    # 下面是CAS登录
    session = None
    while session is None:
        user_name = input("请输入您的学号：")
        pass_word = input("请输入CAS密码（密码不显示，输入完按回车即可）：")
        session = cas_login(user_name, pass_word)
        if session is None:
            print(FAIL + "请重试...")

    # 不再手动设置 head['cookie']，后续所有请求使用 session
    # 但 head 仍然保留用于 User-Agent 等，但不再包含 cookie

    semester_info = loads(
        session.post('https://tis.sustech.edu.cn/Xsxk/queryXkdqXnxq',
                     data={'mxpylx': 1}, verify=False).text
    )
    print(SUCCESS + f"当前学期是{semester_info['p_xn']}学年第{semester_info['p_xq']}学期，为"
                    f"{['', '秋季', '春季', '小'][int(semester_info['p_xq'])]}学期")
    # 然后获取本学期全部课程信息
    print(INFO + "读取程信息...")
    course_info = getinfo(semester_info, session)
    # 分析要喵课程的ID
    for name in course_name_list:
        name = name.strip()
        if name in course_info.keys():
            course_id, course_type = course_info[name]
            course_list.append([course_id, course_type, name])
    print("[\x1b[0;34m{}\x1b[0m]".format("=" * 25))
    for course in course_list:
        print(f"{COURSE_TYPE[course[1]]} : {course[2]}\t\tID为: {course[0]}")
    print("[\x1b[0;34m{}\x1b[0m]".format("=" * 25))
    print(SUCCESS + "成功读入以上信息\n")
    # 喵课主逻辑
    while True:
        while course_list:
            if input(STAR + "按一下回车喵三次，多按同时喵多次，任意字符跳过当前课程\n"):
                course_list.pop(0)
            try:
                _thread.start_new_thread(submit, (semester_info, session, 3))
            except Exception as e:
                print(f"[{e}] 线程异常")

"""
# timing is everything!
    import datetime,time
    start = datetime.datetime.strptime(str(datetime.datetime.now().date()) + '12:55', '%Y-%m-%d%H:%M')
    end = datetime.datetime.strptime(str(datetime.datetime.now().date()) + '13:05', '%Y-%m-%d%H:%M')
    while True:
        n_time = datetime.datetime.now()
        if start < n_time < end:
            for c_id in postList:
                try:
                    submit(semester_info, c_id)
                except:
                    pass
            time.sleep(0xdeadbeef)
        time.sleep(0xc0febabe)
"""
