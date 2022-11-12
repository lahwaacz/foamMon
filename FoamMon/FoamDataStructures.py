from colorama import Fore, Back, Style
import datetime
import os
import sys

import time
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from .Log import Log
from .header import foamMonHeader


def timedelta(seconds):
    return datetime.timedelta(seconds=int(max(0, seconds)))


default_elements = ["progressbar", "folder", "logfile", "time", "writeout", "remaining"]

class ColoredProgressBar():


    events = []

    def __init__(self, size, progress=0):
        self.size = size
        self.done_char = Fore.GREEN + "█" + Style.RESET_ALL
        self.undone_char = Fore.BLUE + "█" + Style.RESET_ALL
        self.digits = [self.done_char
                for _ in range(int(progress*size))]
        self.digits.extend([self.undone_char
                for _ in range(size - int(progress*size))])


    def add_event(self, percentage, color):
        index = int(percentage*self.size)
        self.digits[index] = color + "█" + Style.RESET_ALL

    def draw(self):
        return "".join(self.digits)

class ProgressBar():


    events = []

    def __init__(self, size, progress=0):
        self.size = size
        self.done_char = "█"
        self.undone_char = "░"
        self.digits = [self.done_char
                for _ in range(int(progress*size))]
        self.digits.extend([self.undone_char
                for _ in range(size - int(progress*size))])


    def add_event(self, percentage, color):
        index = int(percentage*self.size)
        self.digits[index] = "█"

    def draw(self):
        return "".join(self.digits)


class Cases():

    def __init__(self, paths):
        self.paths = paths
        self.cases = defaultdict(list)

        self.running = True
        def worker():
            while self.running:
                self.find_cases()
                for i in range(10):
                    if not self.running:
                        return
                    time.sleep(1)
        self.p = ThreadPoolExecutor(1)
        self.future = self.p.submit(worker)

    def get_valid_cases(self):
        case_stats = {}
        for r, cs in sorted(self.cases.items()):
            for c in cs:
                c.refresh()
                if c.log.active:
                    c.log.refresh()
            case_stats[r] = {
                "active": [c.get_status() for c in cs if c.log.active],
                "inactive": [c.get_status() for c in cs if not c.log.active],
            }
        lengths = self.get_max_lengths(case_stats)
        return lengths, case_stats

    def get_max_lengths(self, statuses):
        lengths = {element: 0 for element in default_elements}
        for n, folder in statuses.items():
            for s in folder.get("active", []):
                for elem in lengths.keys():
                    lengths[elem] = max(lengths[elem], s.lengths[elem])

            for s in folder.get("inactive", []):
                for elem in lengths.keys():
                    lengths[elem] = max(lengths[elem], s.lengths[elem])
        return lengths

    def find_cases(self):
        for path in self.paths:
            for r, dirs, _ in os.walk(path):
                dirs.sort(reverse=True)

                ignore = [
                    "boundaryData",
                    "uniform",
                    "processor",
                    "constant",
                    "TDAC",
                    "lagrangian",
                    "postProcessing",
                    "dynamicCode",
                    "system",
                    "VTK",
                ]

                for d in dirs[:]:
                    for i in ignore:
                        if d.startswith(i):
                            dirs.remove(d)

                for d in dirs:
                    c = Case(os.path.join(r, d))
                    if c.is_valid:
                        exists = False
                        for existing in self.cases[r]:
                            if c.path == existing.path:
                                exists = True
                        if not exists:
                            self.cases[r].append(c)


    # def print_header(self, lengths):
    #     width_progress = lengths[0]
    #     width_folder =  lengths[1] + 2
    #     width_log =  lengths[2] + 2
    #     width_time =  lengths[3] + 2
    #     width_next_write =  max(12, lengths[4] + 2)
    #     width_finishes =  lengths[5] + 2
    #     s = "  {: ^{width_progress}}|{: ^{width_folder}}|{: ^{width_log}}|"
    #     s +="{: ^{width_time}}|{: ^{width_next_write}}|{: ^{width_finishes}}"
    #     s = s.format("Progress", "Folder", "Logfile", "Time", "Next write", "Finishes",
    #             width_progress=width_progress,
    #             width_folder=width_folder,
    #             width_log=width_log,
    #             width_time=width_time,
    #             width_next_write=width_next_write,
    #             width_finishes=width_finishes,
    #             )
    #     print(s)

    def print_legend(self):
        s = "\nLegend: "
        s += Fore.GREEN + "█" + Style.RESET_ALL + " Progress "
        s += Fore.YELLOW + "█"  + Style.RESET_ALL + " Start Sampling "
        s += Style.BRIGHT + "Active"  + Style.RESET_ALL  + " "
        s += Style.DIM + "Inactive"  + Style.RESET_ALL + "\n"
        print(s)

    def print_status(self):
        str_ = "\n".join([c.print_status_short()
            for c in self.cases
            if (c.print_status_short and c.log.active)])
        print(str_)


class Case():

    def __init__(self, path, log_format="log", summary=False, log_filter=None):
        self.path = path
        self.folder = os.path.basename(self.path)
        self.log_format = log_format
        self.log_filter = log_filter

        self.log_fns = []
        self.current_log_fn = ""
        self.current_log = None
        self.refresh()

        if summary and self.log.active:
            ret = self.get_status()
            if ret:
                print(ret)

    @property
    def log(self):
        return self.current_log

    def refresh(self):
        if os.path.exists(self.path):
            self.log_fns = list(self.find_logs(self.log_format))
            current_log_fn = self.find_recent_log_fn()
            if self.current_log_fn != current_log_fn:
                self.current_log_fn = current_log_fn
                self.current_log = Log(current_log_fn, self)
        else:
            self.log_fns = []
            self.current_log_fn = ""
            self.current_log = None

    @property
    def is_valid(self):
        return self.has_controlDict and self.log.is_valid

    @property
    def started_sampling(self):
        return self.simTime > self.startSampling

    @property
    def has_controlDict(self):
        return os.path.exists(self.controlDict_file)

    def status_bar(self, digits=100):
        bar = ProgressBar(digits, self.log.progress)
        bar.add_event(self.startSamplingPerc, Fore.YELLOW)
        return bar.draw()

    def custom_filter_value(self, regex):
        return self.log.get_latest_value(regex, self.log.cached_body)

    def find_logs(self, log_format):
        """ returns a list of filenames and mtimes """
        for entry in os.scandir(self.path):
            # TODO use regex to find logs
            if log_format not in entry.name:
                continue
            yield entry.path, entry.stat().st_mtime

    @property
    def last_timestep_ondisk(self):
        if self.log.is_parallel:
            proc_dir = os.path.join(self.path, "processor0")
            if not os.path.exists(proc_dir):
                return 0
            r, ds, _ = next(os.walk(proc_dir))
            rems = [ "constant",
                    "TDAC"]
            for rem in rems:
                if rem in ds:
                    ds.remove(rem)

            ds = [float(d) for d in ds]
            if ds:
                return max(ds)
            else:
                return 0
        else:
            ts = []
            r, ds, _ = next(os.walk(self.path))
            for t in ds:
                try:
                    tsf = float(t)
                    ts.append(tsf)
                except:
                    pass
            if ts:
                return max(ts)
            else:
                return 0

    def find_recent_log_fn(self):
        try:
            files, mtimes = zip(*self.log_fns)
            latest_index = mtimes.index(max(mtimes))
            return files[latest_index]
        except:
            return False

    @property
    def controlDict_file(self):
        return os.path.join(self.path, "system/controlDict")

    def get_key_controlDict(self, key):
        """ find given key in controlDict """
        # TODO cach controlDict to avoid reopening file
        separator = " "
        key += separator
        try:
            with open(self.controlDict_file) as f:
                for i, line in enumerate(f.readlines()):
                    if key in line:
                        # TODO use regex to sanitise
                        return (line.replace(key, '')
                                .replace(' ', '')
                                .replace(';', '')
                                .replace('\n', ''))
        except FileNotFoundError:
            return None

    def get_float_controlDict(self, key):
        ret = self.get_key_controlDict(key)
        if ret:
            return float(ret)
        else:
            return 0

    @property
    def endTime(self):
        return self.get_float_controlDict("endTime")

    @property
    def writeControl(self):
        return self.get_key_controlDict("writeControl")

    @property
    def writeInterval(self):
        if self.writeControl == "runTime" or self.writeControl == "adjustableRunTime":
            return self.get_float_controlDict("writeInterval")
        else:
            return (self.get_float_controlDict("writeInterval") *
                    self.get_float_controlDict("deltaT"))

    @property
    def startSampling(self):
        return self.get_float_controlDict("startTime")

    @property
    def startSamplingPerc(self):
        if self.endTime == 0:
            return 0
        return self.startSampling / self.endTime

    @property
    def simTime(self):
        return self.log.sim_time

    def get_status(self):
        return Status(
                self,
                self.log.progress,
                # Style.BRIGHT if self.log.active else Style.DIM,
                50,
                self.log.active,
                self.folder,
                os.path.basename(self.log.path),
                self.log.sim_time,
                timedelta(self.log.time_till_writeout()),
                timedelta(self.log.timeleft()),
                # Style.RESET_ALL
            )

    def print_status_full(self):
        while True:
            self.log.print_log_body()
            try:
                prog_prec = self.log.progress * 100
                print(self.status_bar(100))
                print("Case properties: ")
                print("Exec: ", self.log.Exec)
                print("Job start time: ", self.log.start_time)
                print("Job elapsed time: ", timedelta(seconds=self.log.wall_time))
                print("Active: ", self.log.active)
                print("Parallel: ", self.log.is_parallel)
                print("Case end time: ", self.endTime)
                print("Current sim time: ", self.log.sim_time)
                print("Last time step on disk: ", self.last_timestep_ondisk)
                print("Time next writeout: ", timedelta(self.log.time_till_writeout()))
                print("Progress: ", prog_prec)
                print("Timeleft: ", timedelta(self.log.timeleft()))
            except Exception as e:
                print(e)
                pass
            self.log.refresh()
            time.sleep(0.2)


class Status():
    """ Handle status of single case for simple printing  """

    def __init__(self, case, progress, digits, active, folder, logfile, time, writeout, remaining):
        self.case = case
        self.progress = progress
        self.digits = digits
        self.active = active
        self.folder = folder
        self.logfile = logfile
        self.time = str(time)
        self.writeout = str(writeout)
        self.remaining = str(remaining)

    @property
    def lengths(self):
        """ returns the lengths of the returned strings """
        return {"progressbar": self.digits,
                "folder": len(self.folder),
                "logfile": len(self.logfile),
                "time": len(self.time),
                "writeout": len(self.writeout),
                "remaining": len(self.remaining),
                }

    def custom_filter(self, value):
        return self.case.custom_filter_value(value)

