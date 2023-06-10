
# (C) 2012, Michael DeHaan, <michael.dehaan@gmail.com>
# (c) 2017 Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)

__metaclass__=type

DOCUMENTATION='''
    callback: log_plays
    type: notification
    short_description: write playbook output to log file
    version_added: historical
    description:
      - This callback writes playbook output to a file per host in the `/var/log/ansible/hosts` directory
      - "TODO: make this configurable"
    requirements:
     - Whitelist in configuration
     - A writeable /var/log/ansible/hosts directory by the user executing Ansbile on the controller
'''

import os
import time
import json
import datetime
import re
from collections import MutableMapping
from ansible.module_utils._text import to_bytes
from ansible.plugins.callback import CallbackBase
from ansible.playbook.task_include import TaskInclude
from ansible import utils
from ansible import constants as C
from ansible.utils.color import colorize, hostcolor
import json
import unicodedata


# NOTE: in Ansible 1.2 or later general logging is available without
# this plugin, just set ANSIBLE_LOG_PATH as an environment variable
# or log_path in the DEFAULTS section of your ansible configuration
# file.  This callback is an example of per hosts logging for those
# that want it.

class CallbackModule (CallbackBase):
    """
    logs playbook results, per host, in /var/log/ansible/hosts
    """
    CALLBACK_VERSION=2.0
    CALLBACK_TYPE='notification'
    CALLBACK_NAME='zs_failed_nodes'
    CALLBACK_NEEDS_WHITELIST=True

    MSG_FORMAT="%(now)s - %(host)s - %(category)s - %(data)s\n\n"
    global filedate
    filedate=datetime.datetime.now ().strftime ("%Y-%m-%d-%H-%M")

    def __init__(self):

        self._play=None
        self._last_task_banner=None
        super (CallbackModule, self).__init__ ()
        self.success_tasks={}
        self.vertical_failed_tasks={}
        self.vertical_success_tasks={}
        self.cloud=''

    def v2_runner_on_failed(self, result, ignore_errors=False):
        if (result.task_name) == "Calling CDA Module":
            self.cda_summary(result)
        else:
            self.log(result, ignore_errors=False)

    def log(self, result, ignore_errors=False) :

        delegated_vars=result._result.get ('_ansible_delegated_vars', None)
        self._clean_results (result._result, result._task.action)

        if self._play.strategy == 'free' and self._last_task_banner != result._task._uuid:
            self._print_task_banner (result._task)

        self._handle_exception (result._result)
        self._handle_warnings (result._result)

        if result._task.loop and 'results' in result._result:
            self._process_items (result)

        else:
            if delegated_vars:
                self._display.display (
                    "fatal: [%s -> %s]: FAILED! => %s" % (result._host.get_name (), delegated_vars['ansible_host'],
                                                          self._dump_results (result._result)), color=C.COLOR_ERROR)

                if (result.task_name in self.vertical_failed_tasks.keys ()):
                    self.vertical_failed_tasks[result.task_name]=self.vertical_failed_tasks[result.task_name] + [result._host.get_name ()]
                else:
                    self.vertical_failed_tasks[result.task_name]=[result._host.get_name ()]


            else:
                self._display.display (
                    "fatal: [%s]: FAILED! => %s" % (result._host.get_name (), self._dump_results (result._result)),
                    color=C.COLOR_ERROR)
                self.hostname=result._host.get_name ()

        if ignore_errors:
            self._display.display ("...ignoring", color=C.COLOR_SKIP)

        self.failed_res_json=json.loads (self._dump_results (result._result))

        if (result.task_name in self.vertical_failed_tasks.keys ()):
            self.vertical_failed_tasks[result.task_name]=self.vertical_failed_tasks[result.task_name] + [
                result._host.get_name ()]
        else:
            self.vertical_failed_tasks[result.task_name]=[result._host.get_name ()]

    def cda_summary(self, result):
        data = json.dumps(result._result)
        data = json.loads(data)
        #self._display.display("Result %s" % (data))
        data = data.get("cda").get("output")
        data = json.loads(data)

        for k,v in data.iteritems():
            if v['status'] == "FAILED":
               taskname = v['taskName']
#               self._display.display("Task name and hostname %s and %s" % (taskname, result._host.get_name()))

               if (taskname in self.vertical_failed_tasks.keys()):
                   self.vertical_failed_tasks[taskname] = self.vertical_failed_tasks[taskname] + [
                             result._host.get_name()]
               else:
                   self.vertical_failed_tasks[taskname] = [result._host.get_name()]

    def v2_runner_on_ok(self, result):

        if (result.task_name) == "Calling CDA Module":
            self.cda_summary(result)


        delegated_vars=result._result.get ('_ansible_delegated_vars', None)
        self._clean_results (result._result, result._task.action)

        if self._play.strategy == 'free' and self._last_task_banner != result._task._uuid:
            self._print_task_banner (result._task)

        if isinstance (result._task, TaskInclude):
            return
        elif result._result.get ('changed', False):
            if delegated_vars:
                msg="changed: [%s -> %s]" % (result._host.get_name (), delegated_vars['ansible_host'])
            else:
                msg="changed: [%s]" % result._host.get_name ()
            color=C.COLOR_CHANGED
        else:
            if delegated_vars:
                msg="ok: [%s -> %s]" % (result._host.get_name (), delegated_vars['ansible_host'])
            else:
                msg="ok: [%s]" % result._host.get_name ()
            color=C.COLOR_OK

        self._handle_warnings (result._result)

        if result._task.loop and 'results' in result._result:
            self._process_items (result)
        else:

            if (
                    self._display.verbosity > 0 or '_ansible_verbose_always' in result._result) and '_ansible_verbose_override' not in result._result:
                msg+=" => %s" % (self._dump_results (result._result),)
            self._display.display (msg, color=color)
        self.failed_res="None Failed"


        self.success_res_json=json.loads (self._dump_results (result._result))
        self.success_stdout=self.success_res_json['stdout']
        if (result.task_name in self.vertical_success_tasks.keys ()):
            self.vertical_success_tasks[result.task_name]=self.vertical_success_tasks[result.task_name] + [
                result._host.get_name (), self.success_stdout]
        else:
            self.vertical_success_tasks[result.task_name]=[result._host.get_name (), self.success_stdout]




    def runner_on_failed(self, host, res, ignore_errors=False):
        self.log (host, 'FAILED', res)

    def runner_on_ok(self, host, res):
        self.log (host, 'OK', res)

    def runner_on_skipped(self, host, item=None):
        self.log (host, 'SKIPPED', '...')

    def runner_on_unreachable(self, host, res):
        self.log (host, 'UNREACHABLE', res)

    def runner_on_async_failed(self, host, res, jid):
        self.log (host, 'ASYNC_FAILED', res)

    def playbook_on_import_for_host(self, host, imported_file):
        self.log (host, 'IMPORTED', imported_file)

    def playbook_on_not_import_for_host(self, host, missing_file):
        self.log (host, 'NOTIMPORTED', missing_file)

    def v2_playbook_on_start(self, playbook):
        self.playbook=playbook
        from os.path import basename
        with open ('/z/var/noc/playbook_name.log', 'w+') as f:
            f.write (basename (playbook._file_name))
        self._display.banner ("PLAYBOOK : %s" % basename (playbook._file_name))
        self.playbook_name=basename (playbook._file_name)


    def storeDataInJson(self, dataArray, path):
        jsondata={}
        with open (path, 'w') as outfile:
            json.dump (dataArray, outfile)

    def v2_playbook_on_stats(self, stats):
        nodes_unreachable, nodes_failed, all_nodes=[], [], []
        dataDict={}
        count_all=0
        count_unreachable=0
        count_failed=0
        count_success=0
        self._display.banner ("PLAY RECAP")
        hosts=sorted (stats.processed.keys ())
        for h in hosts:
            t=stats.summarize (h)
            all_nodes.append (h)
            count_all=count_all + 1
            if t['failures'] == 1 or t['failures'] == 0:
                nodes_failed.append (h)
                count_failed=count_failed + 1
            if t['unreachable'] == 1:
                nodes_unreachable.append (h)
                count_unreachable=count_unreachable + 1
        self._display.banner ("Playbook name %s" % (self.playbook_name))

        if len (self.vertical_failed_tasks) > 0:
            self._display.banner ("LIST OF FAILED NODES AND TASKS WHICH FAILED ON THEM\n")
            for k, v in self.vertical_failed_tasks.iteritems ():
                #                self._display.display("DIC %s :" % (self.vertical_failed_tasks))
                self._display.display ("\n")
                self._display.display ("%s:\n" % (colorize (u'TASK', k, C.COLOR_CHANGED)))
                self._display.display ("%s" % (colorize (u'FAILED NODES', ', '.join (v), C.COLOR_ERROR)))
                self._display.display ("SERVICE FAILED ON TOTAL INSTANCES : %s" % (len (v)))
                with open (/z/etc/noc/z-ansible/vipstate.txt, 'w') as vip_state:
                    vip_state.write ("SERVICE FAILED ON VIP STATE : %s" % (len (v)))
                    vip_state.write ("\n")
        else:
            self._display.banner ("NO TASK FAILED", C.COLOR_OK)

        user=os.getlogin ()
        DIRPATH_PRE_REPORT="/z/var/noc/report_creation/" + str (filedate) + "/" + self.cloud + "/" + user + "/pre"
        DIRPATH_POST_REPORT="/z/var/noc/report_creation/" + str (filedate) + "/" + self.cloud + "/" + user + "/post"
        if not os.path.exists (DIRPATH_PRE_REPORT):
            os.makedirs (DIRPATH_PRE_REPORT)
        if not os.path.exists (DIRPATH_POST_REPORT):
            os.makedirs (DIRPATH_POST_REPORT)
        FILEPATH_PRE_REPORT=DIRPATH_PRE_REPORT + "/" + "pre_report" + ".log"
        FILEPATH_POST_REPORT=DIRPATH_POST_REPORT + "/" + "post_report" + ".log"
        json_file_path_pre=DIRPATH_PRE_REPORT + "/{}_data.json"
        json_file_path_post=DIRPATH_POST_REPORT + "/{}_data.json"


        if "all_role_pre" in self.playbook_name:
            with open (FILEPATH_PRE_REPORT, 'w') as all_role_pre:
                all_role_pre.write ("Playbook name:%s\n" % (self.playbook_name))
                all_role_pre.write ("\n")

                if len (nodes_unreachable) > 0:
                    dataDict["unreachable_nodes"]={"node": ','.join (nodes_unreachable), "count": (count_unreachable), "name": "Unreachable Nodes"}
                    all_role_pre.write ("unreachable_nodes=%s \n" % (', '.join (nodes_unreachable)))
                    all_role_pre.write ("unreachable_count=%s \n" % (count_unreachable))
                    all_role_pre.write ("\n")
                else:
                    dataDict["unreachable_nodes"]={"node": '-',
                                                "count": (count_unreachable), "name": "Unreachable Nodes"}
                    all_role_pre.write ("unreachable_nodes=- \n")
                    all_role_pre.write ("unreachable_count=%s \n" % (count_unreachable))
                    all_role_pre.write ("\n")
                    self.storeDataInJson (dataArray=dataDict, path=json_file_path_pre.format ("pre"))


        if "all_role_post" in self.playbook_name:
            with open (FILEPATH_POST_REPORT, 'w') as all_role_post:
                all_role_post.write ("Playbook name:%s\n" % (self.playbook_name))
                all_role_post.write ("\n")
                if len (nodes_unreachable) > 0:
                    dataDict["unreachable_nodes"]={"node": ','.join (nodes_unreachable),
                                                       "count": (count_unreachable), "name": "Unreachable Nodes"}

                    all_role_post.write ("unreachable_nodes=%s \n" % (', '.join (nodes_unreachable)))
                    all_role_post.write ("unreachable_count=%s \n" % (count_unreachable))
                    all_role_post.write ("\n")
                else:
                    dataDict["unreachable_nodes"]={"node": '-',
                                                       "count": (count_unreachable), "name": "Unreachable Nodes"}

                    all_role_post.write ("unreachable_nodes=- \n")
                    all_role_post.write ("unreachable_count=%s \n" % (count_unreachable))
                    all_role_post.write ("\n")
                    self.storeDataInJson (dataArray=dataDict, path=json_file_path_post.format ("post"))


        key_words={'Check service status': 'service', 'Nodes not Auth Ready': 'auth',
                       'Check Weblog lag on SMSM and CLRS': 'webloglag', 'Validate CAFT state of the smca': 'caft', 'Nodes did not receive build' : 'nodes_didnot', 'Standalone cdsc not connected' : 'cds_connected' }
        if "all_role_pre" in self.playbook_name:
            with open (FILEPATH_PRE_REPORT, 'w') as all_role_pre:
                for key in key_words:
                    if key not in self.vertical_failed_tasks:
                        dataDict[key_words[key]]={"node": "-",
                                                      "count": "0", "name": key}

                        all_role_pre.write ("%s_failed_status=- \n" % (key_words[key]))
                        all_role_pre.write ("%s_failed_count=0 \n" % (key_words[key]))
                        all_role_pre.write ("\n")
                for key, value in self.vertical_failed_tasks.iteritems ():
                    if (key in key_words):
                        dataDict[key_words[key]]={"node": ','.join (value),
                                                      "count": len (value), "name": key}
                        all_role_pre.write ("%s_failed_status=%s \n" % (key_words[key], ','.join (value)))
                        all_role_pre.write ("%s_failed_count=%s \n" % (key_words[key], len (value)))
                        all_role_pre.write ("\n")
                    self.storeDataInJson (dataArray=dataDict, path=json_file_path_pre.format ("pre"))
            self._display.display ("PRE PATH %s" % (json_file_path_pre.format ("pre")))

        if "all_role_post" in self.playbook_name:
            with open (FILEPATH_POST_REPORT, 'w') as all_role_post:
                for key in key_words:
                    if key not in self.vertical_failed_tasks:
                        dataDict[key_words[key]]={"node": "-",
                                                      "count": "0", "name": key}

                        all_role_post.write ("%s_failed_status=- \n" % (key_words[key]))
                        all_role_post.write ("%s_failed_count=0 \n" % (key_words[key]))
                        all_role_post.write ("\n")

                for key, value in self.vertical_failed_tasks.iteritems ():
                    if (key in key_words):
                         all_role_post.write ("%s_failed_status=%s \n" % (key_words[key], ','.join (value)))
                         all_role_post.write ("%s_failed_count=%s \n" % (key_words[key], len (value)))
                         all_role_post.write ("\n")
                         dataDict[key_words[key]]={"node": ','.join (value),
                                                      "count": len (value), "name": key}

                    self.storeDataInJson (dataArray=dataDict, path=json_file_path_post.format ("post"))
            self._display.display ("POST PATH %s" % (json_file_path_post.format ("post")))

        if len (self.vertical_success_tasks) > 0:
            key_words={'NSS count': 'nss_count','VZEN count' : 'vzen_count','ZAB count' : 'zab_count', 'ZAB health': 'zab_health','Show Delta' : 'show_delta', 'NSS nodes streaming logs' : 'nss_streaming', 'Number of active ADP' : 'adp_count'}
            if "all_role_pre" in self.playbook_name:

                with open (FILEPATH_PRE_REPORT, 'a') as all_role_pre:
                    for key, value in self.vertical_success_tasks.iteritems ():
                        if (key in key_words):
                            dataDict[key_words[key]]={"count": value[1], "node": "-",
                                                      "name": key}
                            all_role_pre.write ("%s_status=%s \n" % (key_words[key], value[1]))
                            all_role_pre.write ("\n")
                            self.storeDataInJson (dataArray=dataDict, path=json_file_path_pre.format ("pre"))
                self._display.display ("PRE PATH %s" % (json_file_path_pre.format ("pre")))

            if "all_role_post" in self.playbook_name:
                with open (FILEPATH_POST_REPORT, 'a') as all_role_post:
                    for key, value in self.vertical_success_tasks.iteritems ():
                        if (key in key_words):
                            dataDict[key_words[key]]={"count": value[1], "node": "-",
                                                      "name": key}

                            all_role_post.write ("%s_status=%s \n" % (key_words[key], value[1]))
                            all_role_post.write ("\n")
                            self.storeDataInJson (dataArray=dataDict, path=json_file_path_post.format ("post"))
                self._display.display ("POST PATH %s" % (json_file_path_post.format ("post")))

        else:
            self._display.banner ("NO TASK SUCCESS", C.COLOR_OK)

        if count_unreachable > 0:
            self._display.banner ("%s" % (colorize (u'UNREACHABLE COUNT', count_unreachable, C.COLOR_CHANGED)))

        if len (nodes_unreachable) > 0:
            self._display.banner ("LIST OF UNREACHABLE INSTANCES\n")
            self._display.display (
                "%s" % (colorize (u'UNREACHABLE', ', '.join (nodes_unreachable), C.COLOR_UNREACHABLE)))
        else:
            self._display.banner ("\nALL NODES ARE REACHABLE", C.COLOR_OK)

        self._display.display ("", screen_only=True)

        # print custom stats
        if self._plugin_options.get ('show_custom_stats',
                                     C.SHOW_CUSTOM_STATS) and stats.custom:  # fallback on constants for inherited plugins missing docs
            self._display.banner ("CUSTOM STATS: ")
            # per host
            # TODO: come up with 'all_role_pretty format'
            for k in sorted (stats.custom.keys ()):
                if k == '_run':
                    continue
                self._display.display (
                    '\t%s: %s' % (k, self._dump_results (stats.custom[k], indent=1).replace ('\n', '')))

            # print per run custom stats
            if '_run' in stats.custom:
                self._display.display ("", screen_only=True)
                self._display.display (
                    '\tRUN: %s' % self._dump_results (stats.custom['_run'], indent=1).replace ('\n', ''))
            self._display.display ("", screen_only=True)

    def v2_runner_on_skipped(self, result):
        if self._plugin_options.get ('show_skipped_hosts',
                                     C.DISPLAY_SKIPPED_HOSTS):  # fallback on constants for inherited plugins missing docs

            self._clean_results (result._result, result._task.action)

            if self._play.strategy == 'free' and self._last_task_banner != result._task._uuid:
                self._print_task_banner (result._task)

            if result._task.loop and 'results' in result._result:
                self._process_items (result)
            else:
                msg="skipping: [%s]" % result._host.get_name ()
                if (
                        self._display.verbosity > 0 or '_ansible_verbose_always' in result._result) and '_ansible_verbose_override' not in result._result:
                    msg+=" => %s" % self._dump_results (result._result)
                self._display.display (msg, color=C.COLOR_SKIP)

    def v2_runner_on_unreachable(self, result):
        if self._play.strategy == 'free' and self._last_task_banner != result._task._uuid:
            self._print_task_banner (result._task)

        delegated_vars=result._result.get ('_ansible_delegated_vars', None)
        if delegated_vars:
            self._display.display (
                "fatal: [%s -> %s]: UNREACHABLE! => %s" % (result._host.get_name (), delegated_vars['ansible_host'],
                                                           self._dump_results (result._result)),
                color=C.COLOR_UNREACHABLE)
        else:
            self._display.display (
                "fatal: [%s]: UNREACHABLE! => %s" % (result._host.get_name (), self._dump_results (result._result)),
                color=C.COLOR_UNREACHABLE)

    def v2_playbook_on_no_hosts_matched(self):
        self._display.display ("skipping: no hosts matched", color=C.COLOR_SKIP)

    def v2_playbook_on_no_hosts_remaining(self):
        self._display.banner ("NO MORE HOSTS LEFT")

    def v2_playbook_on_task_start(self, task, is_conditional):

        if self._play.strategy != 'free':
            self._print_task_banner (task)

    def _print_task_banner(self, task):
        # args can be specified as no_log in several places: in the task or in
        # the argument spec.  We can check whether the task is no_log but the
        # argument spec can't be because that is only run on the target
        # machine and we haven't run it thereyet at this time.
        #
        # So we give people a config option to affect display of the args so
        # that they can secure this if they feel that their stdout is insecure
        # (shoulder surfing, logging stdout straight to a file, etc).
        args=''
        if not task.no_log and C.DISPLAY_ARGS_TO_STDOUT:
            args=u', '.join (u'%s=%s' % a for a in task.args.items ())
            args=u' %s' % args

        self._display.banner (u"TASK [%s%s]" % (task.get_name ().strip (), args))
        if self._display.verbosity >= 2:
            path=task.get_path ()
            if path:
                self._display.display (u"task path: %s" % path, color=C.COLOR_DEBUG)

        self._last_task_banner=task._uuid

    def v2_playbook_on_cleanup_task_start(self, task):
        self._display.banner ("CLEANUP TASK [%s]" % task.get_name ().strip ())

    def v2_playbook_on_handler_task_start(self, task):
        self._display.banner ("RUNNING HANDLER [%s]" % task.get_name ().strip ())

    def v2_playbook_on_play_start(self, play):
        variable_manager = play.get_variable_manager()
        all_vars = variable_manager.get_vars()['hostvars']
        clouds = {'ZSCLOUD': 'zsc', 'ZSCALERONE': 'one', 'ZSCALER': 'zsn', 'ZSCALERTHREE': 'zs3', 'ZSCALERTWO': 'zs2',
          'ZSCALERFEED': 'fcc', 'ZSCALERBETA': 'beta', 'ZSCALERSCM': 'zscm' }
        for k,v in all_vars.iteritems():
            cloud = v['cloud']
#            self._display.display("value %s" %(cloud))
            self.cloud = clouds[cloud]
#            self._display.display("value %s" %(self.cloud))
            break

        name=play.get_name().strip()
        if not name:
            msg=u"PLAY"
        else:
            msg=u"PLAY [%s]" % name

        self._play=play

        self._display.banner (msg)

    def v2_on_file_diff(self, result):
        if result._task.loop and 'results' in result._result:
            for res in result._result['results']:
                if 'diff' in res and res['diff'] and res.get ('changed', False):
                    diff=self._get_diff (res['diff'])
                    if diff:
                        self._display.display (diff)
        elif 'diff' in result._result and result._result['diff'] and result._result.get ('changed', False):
            diff=self._get_diff (result._result['diff'])
            if diff:
                self._display.display (diff)

    def v2_runner_item_on_ok(self, result):
        delegated_vars=result._result.get ('_ansible_delegated_vars', None)
        self._clean_results (result._result, result._task.action)
        if isinstance (result._task, TaskInclude):
            return
        elif result._result.get ('changed', False):
            msg='changed'
            color=C.COLOR_CHANGED
        else:
            msg='ok'
            color=C.COLOR_OK

        if delegated_vars:
            msg+=": [%s -> %s]" % (result._host.get_name (), delegated_vars['ansible_host'])
        else:
            msg+=": [%s]" % result._host.get_name ()

        msg+=" => (item=%s)" % (self._get_item (result._result),)

        if (
                self._display.verbosity > 0 or '_ansible_verbose_always' in result._result) and '_ansible_verbose_override' not in result._result:
            msg+=" => %s" % self._dump_results (result._result)
        self._display.display (msg, color=color)
        self.failed_res="None Failed"

    def v2_runner_item_on_failed(self, result):

        delegated_vars=result._result.get ('_ansible_delegated_vars', None)
        self._clean_results (result._result, result._task.action)
        self._handle_exception (result._result)

        msg="failed: "
        if delegated_vars:
            msg+="[%s -> %s]" % (result._host.get_name (), delegated_vars['ansible_host'])
        else:
            msg+="[%s]" % (result._host.get_name ())

        self._handle_warnings (result._result)
        self._display.display (
            msg + " (item=%s) => %s" % (self._get_item (result._result), self._dump_results (result._result)),
            color=C.COLOR_ERROR)

    def v2_runner_item_on_skipped(self, result):
        if self._plugin_options.get ('show_skipped_hosts',
                                     C.DISPLAY_SKIPPED_HOSTS):  # fallback on constants for inherited plugins missing docs
            self._clean_results (result._result, result._task.action)
            msg="skipping: [%s] => (item=%s) " % (result._host.get_name (), self._get_item (result._result))
            if (
                    self._display.verbosity > 0 or '_ansible_verbose_always' in result._result) and '_ansible_verbose_override' not in result._result:
                msg+=" => %s" % self._dump_results (result._result)
            self._display.display (msg, color=C.COLOR_SKIP)

    def v2_playbook_on_include(self, included_file):
        msg='included: %s for %s' % (included_file._filename, ", ".join ([h.name for h in included_file._hosts]))
        self._display.display (msg, color=C.COLOR_SKIP)

    def v2_runner_retry(self, result):
        task_name=result.task_name or result._task
        msg="FAILED - RETRYING: %s (%d retries left)." % (
        task_name, result._result['retries'] - result._result['attempts'])
        if (
                self._display.verbosity > 2 or '_ansible_verbose_always' in result._result) and '_ansible_verbose_override' not in result._result:
            msg+="Result was: %s" % self._dump_results (result._result)
        self._display.display (msg, color=C.COLOR_DEBUG)
