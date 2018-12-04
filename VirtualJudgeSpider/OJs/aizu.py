import json
import ssl
import time

from bs4 import BeautifulSoup
from bs4 import element

from VirtualJudgeSpider.OJs.base import Base, BaseParser
from VirtualJudgeSpider.config import Problem, Result
from VirtualJudgeSpider.utils import HtmlTag, HttpUtil

ssl._create_default_https_context = ssl._create_unverified_context


class AizuParser(BaseParser):

    def __init__(self, *args, **kwargs):
        self._static_prefix = 'http://judge.u-aizu.ac.jp/onlinejudge/'
        self._judge_static_string = ['Compile Error', 'Wrong Answer', 'Time Limit Exceed',
                                     'Memory Limit Exceed', 'Accepted', 'Waiting',
                                     'Output Limit Exceed', 'Runtime Error', 'Presentation Error', 'Running']
        self._script = """<script type="text/x-mathjax-config">
   MathJax.Hub.Config({
    showProcessingMessages: false,
    messageStyle: "none",
    extensions: ["tex2jax.js"],
    jax: ["input/TeX", "output/HTML-CSS"],
    tex2jax: {
        inlineMath:  [ ["$", "$"] ],
        displayMath: [ ["$$","$$"] ],
        skipTags: ['script', 'noscript', 'style', 'textarea', 'pre','code','a']
    },
    "HTML-CSS": {
        availableFonts: ["STIX","TeX"],
        showMathMenu: false
    }
   });
  </script>
  <script src="https://cdn.bootcss.com/mathjax/2.7.0/MathJax.js?config=TeX-AMS-MML_HTMLorMML"></script>"""

    def problem_parse(self, response, pid, url):
        problem = Problem()

        problem.remote_id = pid
        problem.remote_oj = 'Aizu'
        problem.remote_url = url
        if response is None:
            problem.status = Problem.Status.STATUS_SUBMIT_FAILED
            return problem
        website_data = response.text
        status_code = response.status_code
        if status_code in [401, 404]:
            problem.status = Problem.Status.STATUS_PROBLEM_NOT_EXIST
            return problem
        elif status_code != 200:
            problem.status = Problem.Status.STATUS_SUBMIT_FAILED
            return problem
        site_data = json.loads(website_data)
        soup = BeautifulSoup(site_data.get('html'), 'lxml')
        problem.title = str(soup.find('h1').get_text())
        problem.time_limit = str(site_data.get('time_limit')) + ' sec'
        problem.memory_limit = str(site_data.get('memory_limit')) + ' KB'
        problem.special_judge = False

        problem.html = ''

        for tag in soup.body:
            if type(tag) == element.Tag and tag.name in ['p', 'h2', 'pre', 'center']:
                if not tag.get('class'):
                    tag['class'] = ()
                if tag.name == 'h2':
                    tag['style'] = HtmlTag.TagStyle.TITLE.value
                    tag['class'] += (HtmlTag.TagDesc.TITLE.value,)
                else:
                    tag['style'] = HtmlTag.TagStyle.CONTENT.value
                    tag['class'] += (HtmlTag.TagDesc.CONTENT.value,)
                problem.html += str(HtmlTag.update_tag(tag, self._static_prefix))
        problem.html += self._script
        problem.status = Problem.Status.STATUS_CRAWLING_SUCCESS
        return problem

    def result_parse(self, response):
        result = Result()

        if response is None or response.status_code != 200:
            result.status = Result.Status.STATUS_SUBMIT_FAILED
            return result

        website_data = response.text
        site_data = json.loads(website_data)
        submission_record = site_data['submissionRecord']
        result.origin_run_id = str(submission_record['judgeId'])
        result.verdict = self._judge_static_string[int(submission_record['status'])]
        result.execute_time = str(format(float(submission_record['cpuTime']) / float(100), '.2f')) + ' s'
        result.execute_memory = str(submission_record['memory']) + ' KB'
        result.status = Result.Status.STATUS_RESULT
        return result


class Aizu(Base):

    def __init__(self, *args, **kwargs):
        self._headers = {'Content-Type': 'application/json'}

        self._req = HttpUtil(custom_headers=self._headers, *args, **kwargs)

    # 主页链接
    @staticmethod
    def home_page_url():
        url = 'https://onlinejudge.u-aizu.ac.jp/'
        return url

    def set_cookies(self, cookies):
        if type(cookies) == dict:
            self._req.cookies.update(cookies)

    def get_cookies(self):
        return self._req.cookies.get_dict()

    # 登录页面
    def login_website(self, account, *args, **kwargs):
        if account and account.cookies:
            self._req.cookies.update(account.cookies)
        if self.check_login_status():
            return True
        login_link_url = 'https://judgeapi.u-aizu.ac.jp/session'
        post_data = {
            'id': account.username,
            'password': account.password
        }
        self._req.post(url=login_link_url, json=post_data)
        return self.check_login_status()

    # 检查登录状态
    def check_login_status(self):
        url = 'https://judgeapi.u-aizu.ac.jp/self'
        res = self._req.get(url)
        if res and res.status_code == 200:
            return True
        return False

    # 获取题目
    def get_problem(self, *args, **kwargs):
        pid = kwargs['pid']
        url = 'https://judgeapi.u-aizu.ac.jp/resources/descriptions/en/' + str(pid)
        res = self._req.get(url)
        return AizuParser().problem_parse(res, pid, url)

    # 提交代码
    def submit_code(self, *args, **kwargs):
        if not self.login_website(*args, **kwargs):
            return False
        url = 'https://judgeapi.u-aizu.ac.jp/submissions'

        pid = kwargs['pid']
        language = kwargs['language']
        source_code = kwargs['code']
        res = self._req.post(url, json={'problemId': str(pid), 'language': str(language),
                                        'sourceCode': str(source_code)})
        if res and res.status_code == 200:
            return True
        return False

    # 获取当然运行结果
    def get_result(self, *args, **kwargs):
        account = kwargs.get('account')
        pid = str(kwargs.get('pid'))
        url = 'https://judgeapi.u-aizu.ac.jp/submission_records/users/' + str(account.username) + '/problems/' + pid

        time.sleep(3)
        res = self._req.get(url)
        if res is None or res.status_code != 200:
            return None

        recent_list = json.loads(res.text)
        url = 'https://judgeapi.u-aizu.ac.jp/verdicts/' + str(recent_list[0].get('judgeId'))
        return self.get_result_by_url(url)

    # 根据源OJ的运行id获取结构
    def get_result_by_rid_and_pid(self, rid, pid):
        url = 'https://judgeapi.u-aizu.ac.jp/verdicts/' + str(rid)
        return self.get_result_by_url(url)

    # 根据源OJ的url获取结果
    def get_result_by_url(self, url):
        res = self._req.get(url)
        return AizuParser().result_parse(res)

    # 获取源OJ支持的语言类型
    def find_language(self, *args, **kwargs):
        return {'C': 'C', 'C++': 'C++', 'JAVA': 'JAVA', 'C++11': 'C++11', 'C++14': 'C++14', 'C#': 'C#', 'D': 'D',
                'Go': 'Go', 'Ruby': 'Ruby', 'Rust': 'Rust', 'Python': 'Python', 'Python3': 'Python3',
                'JavaScript': 'JavaScript', 'Scala': 'Scala', 'Haskell': 'Haskell', 'OCaml': 'OCaml', 'PHP': 'PHP',
                'Kotlin': 'Kotlin'}

    # 检查源OJ是否运行正常
    def check_status(self):
        url = 'https://judgeapi.u-aizu.ac.jp/categories'
        res = self._req.get(url)
        if res and res.status_code == 200:
            return True
        return False

    @staticmethod
    def is_accepted(verdict):
        return verdict == 'Accepted'

    @staticmethod
    def is_running(verdict):
        return verdict in ['Waiting', 'Running']

    @staticmethod
    def is_compile_error(verdict):
        return verdict == 'Compile Error'


"""
# values of submission status
STATE_COMPILEERROR = 0
STATE_WRONGANSWER = 1
STATE_TIMELIMIT = 2
STATE_MEMORYLIMIT = 3
STATE_ACCEPTED = 4
STATE_WAITING = 5
STATE_OUTPUTLIMIT = 6
STATE_RUNTIMEERROR = 7
STATE_PRESENTATIONERROR = 8
STATE_RUNNING = 9
"""
