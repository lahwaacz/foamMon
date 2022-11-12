import os
import re
import time

# max bytes of log that is read at once
LEN_CACHE_BYTES = 100 * 1024

class Log():

    def __init__(self, path, case):
        self.path = path
        self.case = case

        if self.path:
            self.file = open(self.path, "rb")
            self.mtime = os.path.getmtime(self.path)
            self.cached_header = self.read_header()
            self.cached_body = self.read_tail()
        else:
            self.file = None
            self.mtime = None
            self.cached_header = ""
            self.cached_body = ""

    def __del__(self):
        if self.file is not None:
            self.file.close()

    def read_header(self):
        """ read LEN_CACHE_BYTES bytes from the beginning of the log """
        # seek to the beginning of the file
        self.file.seek(0, os.SEEK_SET)
        # read the header
        header = self.file.read(LEN_CACHE_BYTES).decode("utf-8")
        # end the header somewhere after the first occurrence of ClockTime
        ctime = header.find("ClockTime")
        padding = min(ctime+100, len(header))
        header = header[0:padding] # use 100 padding chars
        return header

    def read_tail(self):
        """ read LEN_CACHE_BYTES bytes from the end of the log """
        # seek before the end
        try:
            self.file.seek(-LEN_CACHE_BYTES, os.SEEK_END)
        except OSError:
            # the seek call above fails when the file is shorter than LEN_CACHE_BYTES
            self.file.seek(0, os.SEEK_SET)
        # read the bytes
        tail = self.file.read(LEN_CACHE_BYTES)
        # skip until the first '\n' byte before decoding
        # (it might contain an incomplete multibyte character)
        tail = tail[tail.find(b"\n"):]
        # return the decoded text
        return tail.decode("utf-8")

    def refresh(self):
        mtime = os.path.getmtime(self.path)
        if self.mtime < mtime:
            self.cached_body = self.read_tail()
            self.mtime = mtime

    @property
    def is_valid(self):
        # TODO Fails on decompose logs
        if not self.path:
            return False
        if self.Exec == "decomposePar" or self.Exec == "blockMesh" or self.Exec == "mapFields":
            return False
        try:
            self.get_SimTime(self.cached_body)
            return True
        except Exception as e:
            # print("Invalid Log", e)
            return False

    @property
    def is_parallel(self):
        return "-parallel" in self.Exec

    @property
    def Exec(self):
        return self.get_header_value("Exec")

    @property
    def nProcs(self):
        return self.get_header_value("nProcs")

    @property
    def Host(self):
        return self.get_header_value("Host")

    @property
    def Case(self):
        return self.get_header_value("Case")

    @property
    def active(self):
        if not self.path:
            return False
        mtime = os.path.getmtime(self.path)
        return (time.time() - mtime) < 60

    def get_values(self, regex, chunk):
        return re.findall(regex, chunk)

    def get_latest_value(self, regex, chunk):
        return self.get_values(regex, chunk)[-1]

    def get_latest_value_or_default(self, regex, chunk, default):
        try:
            return self.get_values(regex, chunk)[-1]
        except IndexError:
            return default

    def get_ClockTime(self, chunk, last=True):
        # NOTE some solver print only the ExecutionTime, thus both times are searched
        # if Execution and Clocktime are presented both are found and ExecutionTime
        # is discarded later
        regex = "(?:Execution|Clock)Time = ([0-9.]*) s"
        return float(self.get_latest_value_or_default(regex, chunk, 0.0))

    def get_SimTime(self, chunk):
        regex = "\nTime = ([0-9.e\-]*)"
        return float(self.get_latest_value_or_default(regex, chunk, 0.0))

    def get_header_value(self, key):
        ret = re.findall("{: <7}: (.+)".format(key), self.cached_header)
        if ret:
            return ret[0]
        return None

    def text(self, filter_):
        lines = self.read_tail().split("\n")
        if filter_:
            return "\n".join([l for l in lines if filter_ in l])
        return "\n".join(lines)

    def print_log_body(self):
        sep_width = 120
        print(self.path)
        print("="*sep_width)
        if self.case.log_filter:
            lines = self.cached_body.split("\n")
            filt_lines = [l for l in lines if self.case.log_filter in l][-30:-1]
            body_str = ("\n".join(filt_lines))
        else:
            body_str = ("\n".join(self.cached_body.split("\n")[-30:-1]))
        print(body_str)

    @property
    def start_time(self):
        return self.get_SimTime(self.cached_header)

    @property
    def sim_time(self):
        return self.get_SimTime(self.cached_body)

    @property
    def wall_time(self):
        return self.get_ClockTime(self.cached_body)

    @property
    def elapsed_sim_time(self):
        return self.sim_time - self.start_time

    @property
    def progress(self):
        if self.case.endTime == 0:
            return 0
        return self.sim_time / self.case.endTime

    @property
    def sim_speed(self):
        return max(1e-12, self.elapsed_sim_time / max(1.0, self.wall_time))

    def timeleft(self):
        return self.time_till(self.case.endTime)

    def time_till_writeout(self):
        return self.time_till(self.case.last_timestep_ondisk + self.case.writeInterval)

    def time_till(self, end):
        return (end - self.sim_time) / self.sim_speed

