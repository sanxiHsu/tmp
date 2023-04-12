# -*- coding: utf-8 -*-
from flask import Flask
from flask import request
import json
import logging
import datetime
from urllib.request import urlopen, Request
from smtplib import SMTP, SMTPException
from email.header import Header
from email.mime.text import MIMEText
import pulsar


app = Flask(__name__)
msg = ""
alert_name = ""
platform_alert_dict = {}
email_group = []
sms_group = []
alert_email_str = ''
alert_sms_str = ''
# log configuration
logging.basicConfig(filename='/sms-api/sms-api.log',
                    format='%(asctime)s -%(levelname)s-%(module)s:%(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S %p',
                    level=logging.DEBUG)
# sms configuration
sms_server = 'http://11.11.11.11/services/smsService?wsdl'
receiver_mob = ['11111111111', '22222222222']
# email configuration
email_server = "11.11.11.11"
email_port = "25"
email_user = "666@citics.com"
# email_password = "mgeuexbkubzbgpmt"
email_receivers = ['555@citics.com', '777@555.com']
# pulsar configuration
token = "235sdgsfh=="
pulsar_token = pulsar.AuthenticationToken(token=token)
try:
    client = pulsar.Client(service_url='pulsar://22.22.22.22:6650', authentication=pulsar_token)
    alert_producer = client.create_producer(topic='mgmt/monitoring/alerts')
    src_alert_producer = client.create_producer(topic='mgmt/monitoring/src_alerts')
except Exception as unreachable:
    logging.error(unreachable)


def format_datetime(utc_time_str, utc_format="%Y-%m-%dT%H:%M:%S.%fZ"):
    utc_time = datetime.datetime.strptime(utc_time_str, utc_format)
    localtime = utc_time + datetime.timedelta(hours=8)
    return localtime


def send_email(alert_msg, platform):
    messages = MIMEText(alert_msg, "plain", "utf-8")
    messages['Subject'] = Header(platform, 'utf-8')

    try:
        smtp_object = SMTP()
        smtp_object.connect(email_server, 25)
        # smtp_object.login(email_user)
        smtp_object.sendmail(email_user, email_receivers, messages.as_string())
        logging.info(f'邮件发送成功, 告警平台: {platform}')
    except SMTPException as e:
        logging.error(f'邮件发送失败, 告警平台: {platform},{e}')


def send_sms_message(receivers_mob, sms_msg, platform):
    """
        #调用短信发送接口
        :param receivers_mob: reciver mobile phone number
        :param sms_msg: alert message
        :return:
    """
    for phone_number in receivers_mob:
        postcontent = '<?xml version="1.0" encoding="UTF-8"?>'''
        postcontent += '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        postcontent += '<soap:Header>'
        postcontent += '        <AccountName>aipaas</AccountName>'
        postcontent += '        <BizType>SMS</BizType>'
        postcontent += '        <SysId>141</SysId>'
        postcontent += '</soap:Header>'
        postcontent += '<soap:Body>'
        postcontent += '<ns2:sendMessage xmlns:ns2="http://wsInterface.ws.sms.hjhz.com/">'
        postcontent += '<messageContent>'
        postcontent += '&lt;?xml version="1.0" encoding="UTF-8" standalone="yes"?&gt;'
        postcontent += '&lt;SMS&gt;'
        postcontent += '    &lt;MaxDelayTime&gt;1&lt;/MaxDelayTime&gt;'
        postcontent += '    &lt;MessageType&gt;141&lt;/MessageType&gt;'
        postcontent += '    &lt;MobileTo&gt;' + phone_number + '&lt;/MobileTo&gt;'
        postcontent += '    &lt;MsgId&gt;T09CM3CT3AWFCWF8&lt;/MsgId&gt;'
        postcontent += '    &lt;OrganizationId&gt;000025&lt;/OrganizationId&gt;'
        postcontent += '    &lt;Priority&gt;8&lt;/Priority&gt;'
        postcontent += '    &lt;SendMsg&gt; {0} &lt;/SendMsg&gt;'.format(sms_msg)
        postcontent += '    &lt;UserId&gt;999999&lt;/UserId&gt;'
        postcontent += '&lt;/SMS&gt;'
        postcontent += '</messageContent>'
        postcontent += '</ns2:sendMessage>'
        postcontent += '</soap:Body>'
        postcontent += '</soap:Envelope>'
        req = Request(sms_server, data=postcontent.encode('UTF-8'),
                      headers={'Content-Type': 'text/xml;charset=UTF-8'})
        http_result = urlopen(req).read().decode("utf-8")
        logging.info(http_result)
        logging.info(f"短信发送成功, 告警平台: {platform}")
    return 0


def format_alert_msg(data, platform):
    """
        # 格式化告警文本，并调用通知发送接口
        :param data: alert data from openshift
        :param platform: flag of cloud plaform
        :return: status code
    """
    global alert_name, platform_alert_dict, email_group, sms_group
    # 初始化各告警级别消息队列
    platform_alert_dict[platform] = {"warning": [], "disaster": []}
    email_group = platform_alert_dict.get(platform).get("warning")
    sms_group = platform_alert_dict.get(platform).get("disaster")
    # 获取告警数据
    alert_data = data.get('alerts')
    alert_data_src = json.dumps(alert_data)
    src_alert_producer.send(alert_data_src.encode('utf-8'))
    for alert in alert_data:
        try:
            alert_level = alert.get('labels').get('level')
            # 跳过openshift本身告警
            if not alert_level:
                continue
            # 告警数据处理
            alert_name = alert.get('labels').get('alertname')
            alert_summary = alert.get('annotations').get('summary')
            alert_description = alert.get('annotations').get('description')
            try:
                eval(alert_description)
            except Exception as e:
                logging.warning(e)
                alert_description = str(alert_description)
            else:
                alert_description = eval(alert_description)
                alert_value = float(alert_description.get('当前值'))
                # 浮点数精度为2
                alert_description['当前值'] = round(alert_value, 2)
            alert_status = alert.get('status')
            alert_instance = alert.get('labels').get('instance')
            alert_start_time = format_datetime(alert.get('startsAt'))
            alert_end_time = alert.get('endsAt')
            if alert_end_time != '0001-01-01T00:00:00Z':
                alert_end_time = format_datetime(alert_end_time)
            else:
                alert_end_time = "暂未结束"
            alert_namespace = alert.get('labels').get('namespace')
            # 格式化告警模板
            alert_template = f"""
                        \r========= 监控报警 =========
                        \r告警状态: {alert_status}
                        \r告警级别: {alert_level}
                        \r告警类型: {alert_name}
                        \r告警平台: {platform}
                        \r名称空间: {alert_namespace}
                        \r故障主机: {alert_instance}
                        \r告警摘要: {alert_summary}
                        \r告警详情: {alert_description}
                        \r故障时间: {alert_start_time}
                        \r=========== end ===========
                        """
            if alert_status == "firing":
                if alert_level == "warning" or alert_level == "error":
                    email_group.append(alert_template)
                elif alert_level == "disaster":
                    email_group.append(alert_template)
                    alert_sms_message = f"""
                        \r告警平台: {platform}
                        \r告警级别: {alert_level}
                        \r告警摘要: {alert_summary}
                        \r故障时间: {alert_start_time}
                        """
                    sms_group.append(alert_sms_message)
            # 告警恢复模板
            elif alert_status == "resolved":
                if alert_level == "warning" or alert_level == "error":
                    alert_message = f"""
                        \r========= 异常恢复 =========
                        \r告警状态:{alert_status}
                        \r告警类型:{alert_name}
                        \r告警平台:{platform}
                        \r名称空间:{alert_namespace}
                        \r故障主机:{alert_instance}
                        \r告警摘要:{alert_summary}
                        \r告警详情:{alert_description}
                        \r故障时间:{alert_start_time}
                        \r结束时间:{alert_end_time}
                        \r=========== end ===========
                        """
                    email_group.append(alert_message)
                elif alert_level == "disaster":
                    alert_sms_message = f"""
                        \r告警状态: 已解决
                        \r告警平台: {platform}
                        \r告警摘要: {alert_summary}
                        \r故障时间: {alert_start_time}
                        \r结束时间: {alert_end_time}
                            """
                    email_group.append(alert_sms_message)
                    sms_group.append(alert_sms_message)
        except Exception as e:
            logging.error(str(e))
            return '1'
    return "0"


def send_alert_msg(platform):
    global email_group, sms_group, alert_email_str, alert_sms_str
    if email_group:
        warning_tmp = map(str, email_group)
        alert_email_str = ''.join(warning_tmp)
        send_email(alert_email_str, platform)
        try:
            alert_producer.send(alert_email_str.encode('utf-8'))
        except Exception as e:
            logging.error(str(e))
        email_group = []
        alert_email_str = ''
        # client.close()
    if sms_group:
        disaster_tmp = map(str, sms_group)
        alert_sms_str = ''.join(disaster_tmp)
        send_sms_message(receiver_mob, alert_sms_str, platform)
        sms_group = []
        alert_sms_str = ''


@app.route('/prod_aicloud', methods=['GET', 'POST'])
def prod_aicloud():
    platform = "ai生产云"
    data = json.loads(request.data)
    try:
        format_alert_msg(data, platform)
        send_alert_msg(platform)
        return "0"
    except Exception as e:
        logging.error(str(e))
        return "1"


@app.route('/devaicloud', methods=['GET', 'POST'])
def devaicloud():
    platform = "ai云开发测试云"
    data = json.loads(request.data)
    try:
        format_alert_msg(data, platform)
        send_alert_msg(platform)
        return "0"
    except Exception as e:
        logging.error(str(e))
        return "1"


@app.route('/oacloud', methods=['GET', 'POST'])
def oacloud():
    platform = "办公云"
    data = json.loads(request.data)
    try:
        format_alert_msg(data, platform)
        send_alert_msg(platform)
        return "0"
    except Exception as e:
        logging.error(str(e))
        return "1"


@app.route('/mgmtcloud', methods=['GET', 'POST'])
def mgmtcloud():
    platform = "管理云"
    data = json.loads(request.data)
    try:
        format_alert_msg(data, platform)
        send_alert_msg(platform)
        return "0"
    except Exception as e:
        logging.error(str(e))
        return "1"


@app.route('/devcloud', methods=['GET', 'POST'])
def devcloud():
    platform = "开发测试云"
    data = json.loads(request.data)
    try:
        format_alert_msg(data, platform)
        send_alert_msg(platform)
        return "999"
    except Exception as e:
        logging.error(str(e))
        return "1"


@app.route('/qd-aicloud', methods=['GET', 'POST'])
def qd_aicloud():
    platform = "ai云灾备云"
    data = json.loads(request.data)
    try:
        format_alert_msg(data, platform)
        send_alert_msg(platform)
        return "0"
    except Exception as e:
        logging.error(str(e))
        return "1"


@app.route('/qd_dev_aicloud', methods=['GET', 'POST'])
def qd_dev_aicloud():
    platform = "ai云开发测试云灾备云"
    data = json.loads(request.data)
    try:
        format_alert_msg(data, platform)
        send_alert_msg(platform)
        return "0"
    except Exception as e:
        logging.error(str(e))
        return "1"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9090)
