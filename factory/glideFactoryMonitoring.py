#
# Description:
#   This module implements the functions needed
#   to monitor the glidein factory
#
# Author:
#   Igor Sfiligoi (Dec 11th 2006)
#

import os,os.path
import re,time,copy,string,math,random
import xmlFormat,timeConversion
from condorExe import iexe_cmd,ExeError # i know this is not the most appropriate use of it, but it works

def string_quote_join(arglist):
    l2=[]
    for e in arglist:
        l2.append('"%s"'%e)
    return string.join(l2)

# this class is used in place of the rrdtool
# python module, if that one is not available
class rrdtool_exe:
    def __init__(self):
        self.rrd_bin=iexe_cmd("which rrdtool")[0][:-1]

    def create(self,*args):
        cmdline='%s create %s'%(self.rrd_bin,string_quote_join(args))
        outstr=iexe_cmd(cmdline)
        return

    def update(self,*args):
        cmdline='%s update %s'%(self.rrd_bin,string_quote_join(args))
        outstr=iexe_cmd(cmdline)
        return

    def graph(self,*args):
        cmdline='%s graph %s'%(self.rrd_bin,string_quote_join(args))
        outstr=iexe_cmd(cmdline)
        return
      

############################################################
#
# Configuration
#
############################################################

class MonitoringConfig:
    def __init__(self):
        # set default values
        # user should modify if needed
        self.rrd_step=300       #default to 5 minutes
        self.rrd_heartbeat=1800 #default to 30 minutes, should be at least twice the loop time
        self.rrd_ds_name="val"
        self.rrd_archives=[('AVERAGE',0.8,1,60/5*24*2),      # max precision, keep 2 days
                           ('AVERAGE',0.92,6,2*24*45),       # 30 min precision, keep for a month and a half
                           ('AVERAGE',0.98,24,12*370)        # 2 hour precision, keep for a year
                           ]
        self.rrd_archives_small=[('AVERAGE',0.8,1,60/5*6),   # max precision, keep 6 hours
                                 ('AVERAGE',0.92,6,2*24*2),  # 30 min precision, keep for 2 days
                                 ('AVERAGE',0.98,24,12*45)   # 2 hour precision, keep for a month and a half
                                 ]

        self.rrd_reports=[('hour',3600,0,1),          # an hour worth of data, max resolution, update at every slot
                          ('day',3600*24,0,6),        # a day worth of data, still high resolution, update as if it was medium res
                          ('week',3600*24*7,1,4),     # a week worth of data, medium resolution, update every 2 hours
                          ('month',3600*24*31,1,12),   # a month worth of data, medium resolution, update once a day
                          ('year',3600*24*365,1,7*12)   # a week worth of data, low resolution, update one a week
                          ]
        self.graph_sizes=[('small',200,75),
                          ('large',400,150),
                          ]
        
        # The name of the attribute that identifies the glidein
        self.monitor_dir="monitor/"

        try:
            import rrdtool
            self.rrd_obj=rrdtool
            print "Using rrdtool module"
        except ImportError,e:
            try:
                self.rrd_obj=rrdtool_exe()
                print "Using rrdtool executable"
            except:
                self.rrd_obj=None
                print "Not using rrdtool at all"

        self.attribute_rrd_recmp=re.compile("^(?P<tp>[a-zA-Z]+)_Attribute_(?P<attr>[a-zA-Z]+)\.rrd$")


    def write_file(self,relative_fname,str):
        fname=os.path.join(self.monitor_dir,relative_fname)
        #print "Writing "+fname
        fd=open(fname+".tmp","w")
        try:
            fd.write(str+"\n")
        finally:
            fd.close()

        tmp2final(fname)
        return
    
    def establish_dir(self,relative_dname):
        dname=os.path.join(self.monitor_dir,relative_dname)      
        if not os.path.isdir(dname):
            os.mkdir(dname)
        return

    def find_disk_frontends(self):
        frontends=[]
        fnames=os.listdir(self.monitor_dir)
        for fname in fnames:
            if fname[:9]=="frontend_":
                frontends.append(fname[9:])
        return frontends

    # returns a list of [fname_without_rrd,type,attribute]
    def find_disk_attributes(self,subdir):
        attributes=[]
        fnames=os.listdir(os.path.join(self.monitor_dir,subdir))
        for fname in fnames:
            parse=self.attribute_rrd_recmp.search(fname)
            if parse==None:
                continue # not an attribute rrd
            attributes.append((fname[:-4],parse.group("tp"),parse.group("attr")))
        return attributes
    
    def write_rrd(self,relative_fname,ds_type,time,val,min=None,max=None):
        """
        Create a RRD file, using rrdtool.
        """
        if self.rrd_obj==None:
            return # nothing to do, no rrd bin no rrd creation
        
        #for tp in ((".rrd",self.rrd_archives),(".small.rrd",self.rrd_archives_small)): # disable for now
        for tp in ((".rrd",self.rrd_archives),):
            rrd_ext,rrd_archives=tp
            fname=os.path.join(self.monitor_dir,relative_fname+rrd_ext)
            #print "Writing RRD "+fname
        
            if not os.path.isfile(fname):
                #print "Create RRD "+fname
                if min==None:
                    min='U'
                if max==None:
                    max='U'
                create_rrd(self.rrd_obj,fname,
                           self.rrd_step,rrd_archives,
                           (self.rrd_ds_name,ds_type,self.rrd_heartbeat,min,max))

            #print "Updating RRD "+fname
            try:
                update_rrd(self.rrd_obj,fname,time,val)
            except Exception,e:
                print "Failed to update %s"%fname
        return
    
    #############################################################################

    # Temporarely deprecate the creation of historical XML files
    #
    #def rrd2xml(self,relative_fname,archive_id,freq,
    #            period,relative_rrd_files):
    #    """
    #    Convert one or more RRDs into an XML file using
    #    rrdtool xport.
    #
    #    rrd_files is a list of (rrd_id,rrd_fname)
    #    """
    #
    #    if self.rrd_obj==None:
    #        return # nothing to do, no rrd bin no rrd conversion
    #    
    #    rrd_archive=self.rrd_archives[archive_id]
    #
    #    fname=os.path.join(self.monitor_dir,relative_fname)      
    #    try:
    #        if os.path.getmtime(fname)>(time.time()-self.rrd_step*rrd_archive[2]*freq*(1.0-(random.random()*0.1-0.05))):
    #            return # file to new to see any benefit from an update
    #    except OSError:
    #        pass # file does not exist -> create
    #
    #    #print "Converting RRD into "+fname
    #
    #    # convert relative fnames to absolute ones
    #    rrd_files=[]
    #    for rrd_file in relative_rrd_files:
    #        rrd_files.append((rrd_file[0],os.path.join(self.monitor_dir,rrd_file[1])))
    #
    #    rrd2xml(self.rrd_obj,fname+".tmp",
    #            self.rrd_step*rrd_archive[2], # step in seconds
    #            self.rrd_ds_name,
    #            rrd_archive[0], #ds_type
    #            period,rrd_files)
    #    tmp2final(fname)
    #    return
    #
    #def report_rrds(self,base_fname,
    #                relative_rrd_files):
    #    """
    #    Create default XML files out of the RRD files
    #    """
    #
    #    for r in self.rrd_reports:
    #        pname,period,idx,freq=r
    #        try:
    #            self.rrd2xml(base_fname+".%s.xml"%pname,idx,freq,
    #                         period,relative_rrd_files)
    #        except ExeError,e:
    #            print "WARNING- XML %s.%s creation failed: %s"%(base_fname,pname,e)
    #            
    #    return

    #############################################################################

    def rrd2graph(self,relative_fname,archive_id,freq,
                  period,width,height,
                  title,relative_rrd_files):
        """
        Convert one or more RRDs into a graph using
        rrdtool xport.

        rrd_files is a list of (rrd_id,rrd_fname,graph_style,color,description)
        """

        if self.rrd_obj==None:
            return # nothing to do, no rrd bin no rrd conversion
        
        rrd_archive=self.rrd_archives[archive_id]

        fname=os.path.join(self.monitor_dir,relative_fname)      
        try:
            if os.path.getmtime(fname)>(time.time()-self.rrd_step*rrd_archive[2]*freq*(1.0-(random.random()*0.1-0.05))):
                return # file too new to see any benefit from an update
        except OSError:
            pass # file does not exist -> create

        #print "Converting RRD into "+fname

        # convert relative fnames to absolute ones
        rrd_files=[]
        for rrd_file in relative_rrd_files:
            abs_rrd_fname=os.path.join(self.monitor_dir,rrd_file[1])
            if not os.path.isfile(abs_rrd_fname):
                return # at least one file missing, file creation would fail
            rrd_files.append((rrd_file[0],abs_rrd_fname,rrd_file[2],rrd_file[3]))

        rrd2graph(self.rrd_obj,fname+".tmp",
                  self.rrd_step*rrd_archive[2], # step in seconds
                  self.rrd_ds_name,
                  rrd_archive[0], #ds_type
                  period,width,height,title,rrd_files)
        tmp2final(fname)
        return

    def graph_rrds(self,base_fname,
                   relative_title,relative_rrd_files):
        """
        Create default XML files out of the RRD files
        """

        if len(relative_rrd_files)<1:
            return # nothing to be done

        for r in self.rrd_reports:
            pname,period,idx,freq=r
            title=relative_title+" - last "+pname
            for g in self.graph_sizes:
                gname,width,height=g
                try:
                    self.rrd2graph(base_fname+".%s.%s.png"%(pname,gname),idx,freq,
                                   period,width,height,title,relative_rrd_files)
                except ExeError,e:
                    print "WARNING- graph %s.%s.%s creation failed: %s"%(base_fname,pname,gname,e)
                    
        return

# global configuration of the module
monitoringConfig=MonitoringConfig()

############################################################
#
# Status 
#
############################################################

class condorQStats:
    def __init__(self):
        self.data={}
        self.updated=time.time()

        self.files_updated=None

    def logSchedd(self,client_name,qc_status):
        """
        qc_status is a dictionary of condor_status:nr_jobs
        """
        if self.data.has_key(client_name):
            t_el=self.data[client_name]
        else:
            t_el={}
            self.data[client_name]=t_el

        el={}
        t_el['Status']=el

        status_pairs=((1,"Idle"), (2,"Running"), (5,"Held"), (1001,"Wait"),(1002,"Pending"),(1100,"IdleOther"))
        for p in status_pairs:
            nr,str=p
            if qc_status.has_key(nr):
                el[str]=qc_status[nr]
            else:
                el[str]=0
        self.updated=time.time()

    def logRequest(self,client_name,requests,params):
        """
        requests is a dictinary of requests
        params is a dictinary of parameters

        At the moment, it looks only for
          'IdleGlideins'
          'MaxRunningGlideins'
        """
        if self.data.has_key(client_name):
            t_el=self.data[client_name]
        else:
            t_el={}
            self.data[client_name]=t_el

        el={}
        t_el['Requested']=el

        if requests.has_key('IdleGlideins'):
            el['Idle']=requests['IdleGlideins']
        if requests.has_key('MaxRunningGlideins'):
            el['MaxRun']=requests['MaxRunningGlideins']

        el['Parameters']=copy.deepcopy(params)

        self.updated=time.time()

    def logClientMonitor(self,client_name,client_monitor,client_internals):
        """
        client_monitor is a dictinary of monitoring info
        client_internals is a dictinary of internals

        At the moment, it looks only for
          'Idle'
          'Running'
          'LastHeardFrom'
        """
        if self.data.has_key(client_name):
            t_el=self.data[client_name]
        else:
            t_el={}
            self.data[client_name]=t_el

        el={}
        t_el['ClientMonitor']=el

        if client_monitor.has_key('Idle'):
            el['Idle']=client_monitor['Idle']
        if client_monitor.has_key('Running'):
            el['Running']=client_monitor['Running']
        if client_internals.has_key('LastHeardFrom'):
            el['InfoAge']=int(time.time()-long(client_internals['LastHeardFrom']))
            el['InfoAgeAvgCounter']=1 # used for totals since we need an avg in totals, not absnum 

        self.updated=time.time()

    def get_data(self):
        data1=copy.deepcopy(self.data)
        for f in data1.keys():
            fe=data1[f]
            for w in fe.keys():
                el=fe[w]
                for a in el.keys():
                    if a[-10:]=='AvgCounter': # do not publish avgcounter fields... they are internals
                        del el[a]
            
        return data1

    def get_xml_data(self,indent_tab=xmlFormat.DEFAULT_TAB,leading_tab=""):
        data=self.get_data()
        return xmlFormat.dict2string(data,
                                     dict_name="frontends",el_name="frontend",
                                     subtypes_params={"class":{'subclass_params':{'Requested':{'dicts_params':{'Parameters':{'el_name':'Parameter'}}}}}},
                                     indent_tab=indent_tab,leading_tab=leading_tab)

    def get_total(self):
        total={'Status':None,'Requested':None,'ClientMonitor':None}

        for f in self.data.keys():
            fe=self.data[f]
            for w in fe.keys():
                if total.has_key(w): # ignore eventual not supported classes
                    el=fe[w]
                    tel=total[w]

                    if tel==None:
                        # first one, just copy over
                        total[w]={}
                        tel=total[w]
                        for a in el.keys():
                            if type(el[a])==type(1): # copy only numbers
                                tel[a]=el[a]
                    else:
                        # successive, sum 
                        for a in el.keys():
                            if type(el[a])==type(1): # consider only numbers
                                if tel.has_key(a):
                                    tel[a]+=el[a]
                            # if other frontends did't have this attribute, ignore
                        # if any attribute from prev. frontends are not in the current one, remove from total
                        for a in tel.keys():
                            if not el.has_key(a):
                                del tel[a]
                            elif type(el[a])!=type(1):
                                del tel[a]
        
        for w in total.keys():
            if total[w]==None:
                del total[w] # remove entry if not defined
            else:
                tel=total[w]
                for a in tel.keys():
                    if a[-10:]=='AvgCounter':
                        # this is an average counter, calc the average of the referred element
                        # like InfoAge=InfoAge/InfoAgeAvgCounter
                        aorg=a[:-10]
                        tel[aorg]=tel[aorg]/tel[a]
                        # the avgcount totals are just for internal purposes
                        del tel[a]

        return total
    
    def get_xml_total(self,indent_tab=xmlFormat.DEFAULT_TAB,leading_tab=""):
        total=self.get_total()
        return xmlFormat.class2string(total,
                                      inst_name="total",
                                      indent_tab=indent_tab,leading_tab=leading_tab)

    def get_updated():
        return self.updated

    def get_xml_updated(self,indent_tab=xmlFormat.DEFAULT_TAB,leading_tab=""):
        xml_updated={"UTC":{"unixtime":timeConversion.getSeconds(self.updated),
                            "ISO8601":timeConversion.getISO8601_UTC(self.updated),
                            "RFC2822":timeConversion.getRFC2822_UTC(self.updated)},
                     "Local":{"ISO8601":timeConversion.getISO8601_Local(self.updated),
                              "RFC2822":timeConversion.getRFC2822_Local(self.updated),
                              "human":timeConversion.getHuman(self.updated)}}
        return xmlFormat.dict2string(xml_updated,
                                     dict_name="updated",el_name="timezone",
                                     subtypes_params={"class":{}},
                                     indent_tab=indent_tab,leading_tab=leading_tab)


    def write_file(self):
        global monitoringConfig

        if (self.files_updated!=None) and ((self.updated-self.files_updated)<5):
            # files updated recently, no need to redo it
            return 
        

        # write snaphot file
        xml_str=('<?xml version="1.0" encoding="ISO-8859-1"?>\n\n'+
                 '<glideFactoryEntryQStats>\n'+
                 self.get_xml_updated(indent_tab=xmlFormat.DEFAULT_TAB,leading_tab=xmlFormat.DEFAULT_TAB)+"\n"+
                 self.get_xml_data(indent_tab=xmlFormat.DEFAULT_TAB,leading_tab=xmlFormat.DEFAULT_TAB)+"\n"+
                 self.get_xml_total(indent_tab=xmlFormat.DEFAULT_TAB,leading_tab=xmlFormat.DEFAULT_TAB)+"\n"+
                 "</glideFactoryEntryQStats>\n")
        monitoringConfig.write_file("schedd_status.xml",xml_str)

        data=self.get_data()
        total_el=self.get_total()

        # update RRDs
        for fe in [None]+data.keys():
            if fe==None: # special key == Total
                fe_dir="total"
                fe_el=total_el
            else:
                fe_dir="frontend_"+fe
                fe_el=data[fe]

            monitoringConfig.establish_dir(fe_dir)
            for tp in fe_el.keys():
                # type - Status, Requested or ClientMonitor
                for a in fe_el[tp].keys():
                    a_el=fe_el[tp][a]
                    if type(a_el)!=type({}): # ignore subdictionaries
                        monitoringConfig.write_rrd("%s/%s_Attribute_%s"%(fe_dir,tp,a),
                                                   "GAUGE",self.updated,a_el)

        self.files_updated=self.updated        
        return
    
    def create_support_history(self):
        global monitoringConfig
        data=self.get_data()
        total_el=self.get_total()

        # create human readable files for each entry + total
        for fe in [None]+data.keys():
            if fe==None: # special key == Total
                fe="total"
                fe_dir="total"
                fe_el=total_el
            else:
                fe_dir="frontend_"+fe
                fe_el=data[fe]

            # create history XML files for RRDs
            # DEPRECATED FOR NOW
            #for tp in fe_el.keys():
            #    # type - status or requested
            #    for a in fe_el[tp].keys():
            #        if type(fe_el[tp][a])!=type({}): # ignore subdictionaries
            #            monitoringConfig.report_rrds("%s/%s_Attribute_%s"%(fe_dir,tp,a),
            #                                         [(a,"%s/%s_Attribute_%s.rrd"%(fe_dir,tp,a))])

            # create graphs for RRDs
            monitoringConfig.graph_rrds("%s/Idle"%fe_dir,
                                        "Idle glideins",
                                        [("Requested","%s/Requested_Attribute_Idle.rrd"%fe_dir,"AREA","00FFFF"),
                                         ("Idle","%s/Status_Attribute_Idle.rrd"%fe_dir,"LINE2","0000FF"),
                                         ("Wait","%s/Status_Attribute_Wait.rrd"%fe_dir,"LINE2","FF00FF"),
                                         ("Pending","%s/Status_Attribute_Pending.rrd"%fe_dir,"LINE2","00FF00"),
                                         ("IdleOther","%s/Status_Attribute_IdleOther.rrd"%fe_dir,"LINE2","FF0000")])
            monitoringConfig.graph_rrds("%s/Running"%fe_dir,
                                        "Running glideins",
                                        [("Running","%s/Status_Attribute_Running.rrd"%fe_dir,"AREA","00FF00")])
            monitoringConfig.graph_rrds("%s/MaxRun"%fe_dir,
                                        "Max running glideins requested",
                                        [("MaxRun","%s/Requested_Attribute_MaxRun.rrd"%fe_dir,"AREA","008000")])
            monitoringConfig.graph_rrds("%s/Held"%fe_dir,
                                        "Held glideins",
                                        [("Held","%s/Status_Attribute_Held.rrd"%fe_dir,"AREA","c00000")])
            monitoringConfig.graph_rrds("%s/ClientIdle"%fe_dir,
                                        "Idle client",
                                        [("Idle","%s/ClientMonitor_Attribute_Idle.rrd"%fe_dir,"AREA","00FFFF"),
                                         ("Requested","%s/Requested_Attribute_Idle.rrd"%fe_dir,"LINE2","0000FF")])
            monitoringConfig.graph_rrds("%s/ClientRunning"%fe_dir,
                                        "Running client jobs",
                                        [("Running","%s/ClientMonitor_Attribute_Running.rrd"%fe_dir,"AREA","00FF00")])
            monitoringConfig.graph_rrds("%s/InfoAge"%fe_dir,
                                        "Client info age",
                                        [("InfoAge","%s/ClientMonitor_Attribute_InfoAge.rrd"%fe_dir,"LINE2","000000")])
            
        # create support index files
        for fe in data.keys():
            fe_dir="frontend_"+fe
            for rp in monitoringConfig.rrd_reports:
                period=rp[0]
                for sz in monitoringConfig.graph_sizes:
                    size=sz[0]
                    fname=os.path.join(monitoringConfig.monitor_dir,"%s/0Status.%s.%s.html"%(fe_dir,period,size))
                    #if (not os.path.isfile(fname)): #create only if it does not exist
                    if 1: # create every time, it is small and works over reconfigs 
                        fd=open(fname,"w")
                        fd.write("<html>\n<head>\n")
                        fd.write("<title>%s over last %s</title>\n"%(fe,period));
                        fd.write("</head>\n<body>\n")
                        fd.write('<table width="100%"><tr>\n')
                        fd.write('<td colspan=4 valign="top" align="left"><h1>%s over last %s</h1></td>\n'%(fe,period))
                        

                        fd.write("</tr><tr>\n")
                        
                        fd.write('<td>[<a href="../total/0Status.%s.%s.html">Entry total</a>]</td>\n'%(period,size))
                        
                        link_arr=[]
                        for ref_sz in monitoringConfig.graph_sizes:
                            ref_size=ref_sz[0]
                            if size!=ref_size:
                                link_arr.append('<a href="0Status.%s.%s.html">%s</a>'%(period,ref_size,ref_size))
                        fd.write('<td align="center">[%s]</td>\n'%string.join(link_arr,' | '));

                        link_arr=[]
                        for ref_rp in monitoringConfig.rrd_reports:
                            ref_period=ref_rp[0]
                            if period!=ref_period:
                                link_arr.append('<a href="0Status.%s.%s.html">%s</a>'%(ref_period,size,ref_period))
                        fd.write('<td align="center">[%s]</td>\n'%string.join(link_arr,' | '));

                        fd.write('<td align="right">[<a href="0Log.%s.%s.html">Log stats</a>]</td>\n'%(period,size))
                        
                        fd.write("</tr></table>\n")

                        fd.write("<h2>Glidein stats</h2>\n")
                        fd.write("<table>")
                        for s in ['Idle','Running','Held']:
                            fd.write('<tr>')
                            fd.write('<td><img src="%s.%s.%s.png"></td>'%(s,period,size))
                            if s=='Running':
                                s1='MaxRun'
                                fd.write('<td><img src="%s.%s.%s.png"></td>'%(s1,period,size))
                            fd.write('</tr>\n')                            
                        fd.write("</table>")
                        fd.write("<h2>Frontend (client) stats</h2>\n")
                        fd.write("<table>")
                        for s in ['ClientIdle','ClientRunning','InfoAge']:
                            fd.write('<tr>')
                            fd.write('<td><img src="%s.%s.%s.png"></td>'%(s,period,size))
                            fd.write('</tr>\n')                            
                        fd.write("</table>")
                        fd.write("</body>\n</html>\n")
                        fd.close()
                        pass

        # create human readable files for total aggregating multiple entries 
        frontend_list=monitoringConfig.find_disk_frontends()
        frontend_list.sort()

        colors=['00ff00','00ffff','ffff00','ff00ff','0000ff','ff0000']
        attr_rrds=monitoringConfig.find_disk_attributes("total")
        for fname,tp,a in attr_rrds:
            rrd_fnames=[]
            idx=0
            for fe in frontend_list:
                area_name="STACK"
                if idx==0:
                    area_name="AREA"
                rrd_fnames.append((string.replace(string.replace(fe,".","_"),"@","_"),"frontend_%s/%s.rrd"%(fe,fname),area_name,colors[idx%len(colors)]))
                idx=idx+1

            if tp=="Status":
                tstr=a
            else:
                tstr="%s %s"%(tp,a)
            monitoringConfig.graph_rrds("total/Split_%s"%fname,
                                        "%s glideins"%tstr,
                                        rrd_fnames)

        # create support index files for total
        fe="Entry Total"
        fe_dir="total"
        for rp in monitoringConfig.rrd_reports:
            period=rp[0]
            for sz in monitoringConfig.graph_sizes:
                size=sz[0]
                fname=os.path.join(monitoringConfig.monitor_dir,"%s/0Status.%s.%s.html"%(fe_dir,period,size))
                #if (not os.path.isfile(fname)): #create only if it does not exist
                if 1: # create every time, it is small and works over reconfigs
                    fd=open(fname,"w")
                    fd.write("<html>\n<head>\n")
                    fd.write("<title>%s over last %s</title>\n"%(fe,period));
                    fd.write("</head>\n<body>\n")
                    fd.write('<table width="100%"><tr>\n')
                    fd.write('<td valign="top" align="left"><h1>%s over last %s</h1></td>\n'%(fe,period))

                    link_arr=[]
                    for ref_sz in monitoringConfig.graph_sizes:
                        ref_size=ref_sz[0]
                        if size!=ref_size:
                            link_arr.append('<a href="0Status.%s.%s.html">%s</a>'%(period,ref_size,ref_size))
                    fd.write('<td align="center">[%s]</td>\n'%string.join(link_arr,' | '));

                    link_arr=[]
                    for ref_rp in monitoringConfig.rrd_reports:
                        ref_period=ref_rp[0]
                        if period!=ref_period:
                            link_arr.append('<a href="0Status.%s.%s.html">%s</a>'%(ref_period,size,ref_period))
                    fd.write('<td align="right">[%s]</td>\n'%string.join(link_arr,' | '));

                    fd.write('<td align="right">[<a href="0Log.%s.%s.html">Log stats</a>]</td>\n'%(period,size))
                        
                    fd.write("</tr><tr>\n")

                    fd.write('<td>[<a href="../../total/0Status.%s.%s.html">Factory total</a>]</td>\n'%(period,size))
                    link_arr=[]
                    for ref_fe in frontend_list:
                        link_arr.append('<a href="../frontend_%s/0Status.%s.%s.html">%s</a>'%(ref_fe,period,size,ref_fe))
                    fd.write('<td colspan=3 align="right">[%s]</td>\n'%string.join(link_arr,' | '));

                    fd.write("</tr></table>\n")

                    fd.write("<h2>Glidein stats</h2>\n")
                    fd.write("<table>")
                    for l in [('Idle','Split_Status_Attribute_Idle','Split_Requested_Attribute_Idle'),
                              ('Split_Status_Attribute_Wait','Split_Status_Attribute_Pending','Split_Status_Attribute_IdleOther'),
                              ('Running','Split_Status_Attribute_Running','Split_Requested_Attribute_MaxRun'),
                              ('Held','Split_Status_Attribute_Held')]:
                        fd.write('<tr valign="top">')
                        for s in l:
                            fd.write('<td><img src="%s.%s.%s.png"></td>'%(s,period,size))
                        fd.write('</tr>\n')                            
                    fd.write("</table>")
                    fd.write("<h2>Frontend (client) stats</h2>\n")
                    fd.write("<table>")
                    for l in [('ClientIdle','Split_ClientMonitor_Attribute_Idle'),
                              ('ClientRunning','Split_ClientMonitor_Attribute_Running'),
                              ('InfoAge','Split_ClientMonitor_Attribute_InfoAge')]:
                        fd.write('<tr valign="top">')
                        for s in l:
                            fd.write('<td><img src="%s.%s.%s.png"></td>'%(s,period,size))
                        fd.write('</tr>\n')                            
                    fd.write("</table>")
                    fd.write("</body>\n</html>\n")
                    fd.close()
                    pass

        return
    
class condorLogSummary:
    def __init__(self):
        self.data={}
        self.updated=time.time()
        self.updated_year=time.localtime(self.updated)[0]
        self.current_stats_data={}     # will contain dictionary client->dirSummary.data
        self.stats_diff={}             # will contain the differences
        self.job_statuses=('Wait','Idle','Running','Held','Completed','Removed') #const

        self.files_updated=None
        self.history_files_updated=None

    def reset(self):
        # reserve only those that has been around this time
        new_stats_data={}
        for c in self.stats_diff.keys():
            new_stats_data[c]=self.current_stats_data[c]

        self.current_stats_data=new_stats_data

        # and flush out the differences
        self.stats_diff={}

    def diffTimes(self,end_time,start_time):
        year=self.updated_year
        try:
            start_list=[year,int(start_time[0:2]),int(start_time[3:5]),int(start_time[6:8]),int(start_time[9:11]),int(start_time[12:14]),0,0,-1]
            end_list=[year,int(end_time[0:2]),int(end_time[3:5]),int(end_time[6:8]),int(end_time[9:11]),int(end_time[12:14]),0,0,-1]
        except ValueError:
            return -1 #invalid

        try:
            start_ctime=time.mktime(start_list)
            end_ctime=time.mktime(end_list)
        except TypeError:
            return -1 #invalid

        if start_ctime<=end_ctime:
            return end_ctime-start_ctime

        # else must have gone over the year boundary
        start_list[0]-=1 #decrease start year
        try:
            start_ctime=time.mktime(start_list)
        except TypeError:
            return -1 #invalid

        return end_ctime-start_ctime

        

    def getTimeRange(self,absval):
        if absval<1:
            return 'Unknown'
        if absval<240:
            return 'TooShort'
        # start with 7.5 min, and than exp2
        logval=int(math.log(absval/450.0,2)+0.49)
        level=math.pow(2,logval)*450.0
        if level<3600:
            return "%imins"%(int(level/60+0.49))
        else:
            return "%ihours"%(int(level/3600+0.49))
            
    def getMillRange(self,absval):
        if absval<0.5:
            return '0m'
        # make sure 1000 gets back to 1000
        logval=int(math.log(absval*1.024,2)+0.49)
        level=int(math.pow(2,logval)/1.024)
        return "%im"%level
            

    def logSummary(self,client_name,stats):
        """
         stats - glideFactoryLogParser.dirSummaryTimingsOut
        """
        if self.current_stats_data.has_key(client_name):
            self.stats_diff[client_name]=stats.diff(self.current_stats_data[client_name])
        else:
            self.stats_diff[client_name]=None # should only compare agains a known result
        
        self.current_stats_data[client_name]=stats.data
        self.updated=time.time()
        self.updated_year=time.localtime(self.updated)[0]

    def get_stats_total(self):
        total={'Wait':None,'Idle':None,'Running':None,'Held':None}
        for k in total.keys():
            total[k]=[]
            tdata=total[k]
            for client_name in self.stats_diff.keys():
                sdata=self.current_stats_data[client_name]
                if ((sdata!=None) and (k in sdata.keys())):
                    tdata=tdata+sdata[k]
        return total

    def get_diff_total(self):
        total={'Wait':None,'Idle':None,'Running':None,'Held':None,'Completed':None,'Removed':None}
        for k in total.keys():
            total[k]={'Entered':[],'Exited':[]}
            tdata=total[k]
            for client_name in self.stats_diff.keys():
                sdiff=self.stats_diff[client_name]
                if ((sdiff!=None) and (k in sdiff.keys())):
                    for e in tdata.keys():
                        tdata[e]=tdata[e]+sdiff[k][e]
        return total

    def write_file(self):
        global monitoringConfig

        if (self.files_updated!=None) and ((self.updated-self.files_updated)<5):
            # files updated recently, no need to redo it
            return 
        
        for client_name in [None]+self.stats_diff.keys():
            if client_name==None:
                fe_dir="total"
                sdata=self.get_stats_total()
                sdiff=self.get_diff_total()
            else:
                fe_dir="frontend_"+client_name
                sdata=self.current_stats_data[client_name]
                sdiff=self.stats_diff[client_name]

            monitoringConfig.establish_dir(fe_dir)
            for s in self.job_statuses:
                if not (s in ('Completed','Removed')): # I don't have their numbers from inactive logs
                    if ((sdata!=None) and (s in sdata.keys())):
                        count=len(sdata[s])
                    else:
                        count=0
                    
                    monitoringConfig.write_rrd("%s/Log_%s_Count"%(fe_dir,s),
                                               "GAUGE",self.updated,count)

                if ((sdiff!=None) and (s in sdiff.keys())):
                    entered_list=sdiff[s]['Entered']
                    entered=len(entered_list)
                    exited=-len(sdiff[s]['Exited'])
                else:
                    entered_list=[]
                    entered=0
                    exited=0
                    
                monitoringConfig.write_rrd("%s/Log_%s_Entered"%(fe_dir,s),
                                           "ABSOLUTE",self.updated,entered)
                if not (s in ('Completed','Removed')): # Always 0 for them
                    monitoringConfig.write_rrd("%s/Log_%s_Exited"%(fe_dir,s),
                                               "ABSOLUTE",self.updated,exited)
                elif s=='Completed':
                    # summarize completed data
                    count_entered_times={}
                    count_validation_failed=0
                    count_waste_mill={'validation':{},
                                 'idle':{},
                                 'nosuccess':{}, #i.e. everything but jobs terminating with 0
                                 'badput':{}} #i.e. everything but jobs terminating
                    # should also add abs waste

                    for enle in entered_list:
                        enle_running_time=enle[2]
                        enle_last_time=enle[3]
                        enle_difftime=self.diffTimes(enle_last_time,enle_running_time)

                        # get stats
                        enle_stats=enle[4]
                        enle_condor_started=0
                        if enle_stats!=None:
                            enle_condor_started=enle_stats['condor_started']
                        if not enle_condor_started:
                            count_validation_failed+=1
                            # 100% waste_mill
                            enle_waste_mill={'validation':1000,
                                        'idle':0,
                                        'nosuccess':1000,
                                        'badput':1000}
                        else:
                            #get waste_mill
                            enle_condor_duration=enle_stats['condor_duration']
                            if enle_condor_duration==None:
                                enle_condor_duration=0 # assume failed

                            if enle_condor_duration>enle_difftime: # can happen... Condor-G has its delays
                                enle_difftime=enle_condor_duration

                            # get wate numbers, in permill
                            if (enle_condor_duration<5): # very short means 100% loss
                                enle_waste_mill={'validation':1000,
                                            'idle':0,
                                            'nosuccess':1000,
                                            'badput':1000}
                            else:
                                enle_condor_stats=enle_stats['stats']
                                enle_waste_mill={'validation':1000.0*(enle_difftime-enle_condor_duration)/enle_difftime,
                                            'idle':1000.0*(enle_condor_duration-enle_condor_stats['Total']['secs'])/enle_difftime}
                                enle_goodput=enle_condor_stats['goodZ']['secs']
                                enle_waste_mill['nosuccess']=1000.0*(enle_difftime-enle_goodput)/enle_difftime
                                enle_goodput+=enle_condor_stats['goodNZ']['secs']
                                enle_waste_mill['badput']=1000.0*(enle_difftime-enle_goodput)/enle_difftime

                        # find and save time range
                        enle_timerange=self.getTimeRange(enle_difftime)                        
                        try:
                            count_entered_times[enle_timerange]+=1
                        except: # easy initialization way
                            count_entered_times[enle_timerange]=1

                        # find and save waste range
                        for w in enle_waste_mill.keys():
                            count_waste_mill_w=count_waste_mill[w]
                            # find and save taime range
                            enle_waste_mill_w_range=self.getMillRange(enle_waste_mill[w])
                            try:
                                count_waste_mill_w[enle_waste_mill_w_range]+=1
                            except: # easy initialization way
                                count_waste_mill_w[enle_waste_mill_w_range]=1


                    # save run times
                    for timerange in count_entered_times.keys():
                        monitoringConfig.write_rrd("%s/Log_%s_Entered_Lasted_%s"%(fe_dir,s,timerange),
                                                   "ABSOLUTE",self.updated,count_entered_times[timerange])
                    # save failures
                    monitoringConfig.write_rrd("%s/Log_%s_Entered_Failed"%(fe_dir,s),
                                               "ABSOLUTE",self.updated,count_validation_failed)

                    # save waste_mill
                    for w in count_waste_mill.keys():
                        count_waste_mill_w=count_waste_mill[w]
                        for p in count_waste_mill_w.keys():
                            monitoringConfig.write_rrd("%s/Log_%s_Entered_Waste_%s_%s"%(fe_dir,s,w,p),
                                                       "ABSOLUTE",self.updated,count_waste_mill_w[p])
                            


        self.files_updated=self.updated
        return
    
    def create_support_history(self):
        global monitoringConfig

        if (self.history_files_updated!=None) and ((self.files_updated-self.history_files_updated)<30):
            # history files updated recently, no need to redo it
            return 

        # create history XML files for RRDs
        # DEPRECATE FOR NOW
        #for client_name in [None]+self.stats_diff.keys():
        #    if client_name==None:
        #        fe_dir="total"
        #    else:
        #        fe_dir="frontend_"+client_name
        #
        #    for s in self.job_statuses:
        #        report_rrds=[('Entered',"%s/Log_%s_Entered.rrd"%(fe_dir,s))]
        #        if not (s in ('Completed','Removed')): # I don't have their numbers from inactive logs
        #            report_rrds.append(('Exited',"%s/Log_%s_Exited.rrd"%(fe_dir,s)))
        #            report_rrds.append(('Count',"%s/Log_%s_Count.rrd"%(fe_dir,s)))
        #        monitoringConfig.report_rrds("%s/Log_%s"%(fe_dir,s),report_rrds);

        # create graphs for RRDs
        colors={"Wait":"00FFFF","Idle":"0000FF","Running":"00FF00","Held":"c00000"}
        r_colors=('c00000','ff0000','ffc000','ffd090','ffff00','e0e0a0','a0e0e0','00ffff','90b0ff','a0ffa0','00ff00','00c000')
        r_colors_len=len(r_colors)
        for client_name in [None]+self.stats_diff.keys():
            if client_name==None:
                fe_dir="total"
            else:
                fe_dir="frontend_"+client_name

            for s in self.job_statuses:
                rrd_files=[('Entered',"%s/Log_%s_Entered.rrd"%(fe_dir,s),"AREA","00ff00")]
                if not (s in ('Completed','Removed')): # always 0 for them
                    rrd_files.append(('Exited',"%s/Log_%s_Exited.rrd"%(fe_dir,s),"AREA","ff0000"))

                monitoringConfig.graph_rrds("%s/Log_%s_Diff"%(fe_dir,s),
                                            "Difference in "+s, rrd_files)

                if not (s in ('Completed','Removed')): # I don't have their numbers from inactive logs
                    monitoringConfig.graph_rrds("%s/Log_%s_Count"%(fe_dir,s),
                                                s,
                                                [(s,"%s/Log_%s_Count.rrd"%(fe_dir,s),"AREA",colors[s])])
                elif s=="Completed":
                    # create graphs for Lasted and Waste
                    client_dir=os.listdir(os.path.join(monitoringConfig.monitor_dir,fe_dir))
                    for t in ("Lasted","Waste_badput","Waste_idle","Waste_nosuccess","Waste_validation"):
                        # get sorted list of rrds
                        t_re=re.compile("Log_Completed_Entered_%s_(?P<count>[0-9]*)(?P<unit>[^.]*).+rrd"%t)
                        t_keys={}
                        for d in client_dir:
                            t_re_m=t_re.match(d)
                            if t_re_m!=None:
                                t_keys[t_re_m.groups()]=1
                        t_keys=t_keys.keys()
                        t_keys_len=len(t_keys)

                        if t_keys_len>0:
                            if t=="Lasted":
                                t_keys.sort(cmpPairs)
                            else:
                                # invert order for Wasted
                                t_keys.sort(lambda x,y,:-cmpPairs(x,y))
                            
                            
                            # Create graph out of it
                            t_rrds=[]
                            idx=0
                            for t_k in t_keys:
                                if t_keys_len>1:
                                  t_k_color=r_colors[int(1.*(r_colors_len-1)*idx/(t_keys_len-1)+0.49)]
                                else:
                                  t_k_color=r_colors[r_colors_len/2]
                                t_rrds.append((str("%s%s"%t_k),str("%s/Log_Completed_Entered_%s_%s%s.rrd"%(fe_dir,t,t_k[0],t_k[1])),"STACK",t_k_color))
                                idx+=1
                            monitoringConfig.graph_rrds("%s/Log_Completed_Entered_%s"%(fe_dir,t),
                                                        t,t_rrds)

                                

        # Crate split graphs for total
        frontend_list=monitoringConfig.find_disk_frontends()
        frontend_list.sort()

        colors=['00ff00','00ffff','ffff00','ff00ff','0000ff','ff0000']
        for s in self.job_statuses:
            diff_rrd_files=[]
            count_rrd_files=[]

            idx=0
            for fe in frontend_list:
                fe_dir="frontend_"+fe
                diff_rrd_files.append(['Entered_%s'%string.replace(string.replace(fe,".","_"),"@","_"),"%s/Log_%s_Entered.rrd"%(fe_dir,s),"STACK",colors[idx%len(colors)]])
                idx=idx+1

            if not (s in ('Completed','Removed')): # I don't have their numbers from inactive logs
                idx=0
                for fe in frontend_list:
                    fe_dir="frontend_"+fe
                    diff_rrd_files.append(['Exited_%s'%string.replace(string.replace(fe,".","_"),"@","_"),"%s/Log_%s_Exited.rrd"%(fe_dir,s),"STACK",string.replace(colors[idx%len(colors)],'f','c')])
                    count_rrd_files.append([string.replace(string.replace(fe,".","_"),"@","_"),"%s/Log_%s_Count.rrd"%(fe_dir,s),"STACK",colors[idx%len(colors)]])
                    idx=idx+1
                monitoringConfig.graph_rrds("total/Split_Log_%s_Count"%s,
                                            s,count_rrd_files)
            
            monitoringConfig.graph_rrds("total/Split_Log_%s_Diff"%s,
                                        "Difference in "+s, diff_rrd_files)

        # create support index files
        for client_name in [None]+self.stats_diff.keys():
            if client_name==None:
                fe_dir="total"
                client_name="Entry total"
            else:
                fe_dir="frontend_"+client_name

            for rp in monitoringConfig.rrd_reports:
                period=rp[0]
                for sz in monitoringConfig.graph_sizes:
                    size=sz[0]
                    fname=os.path.join(monitoringConfig.monitor_dir,"%s/0Log.%s.%s.html"%(fe_dir,period,size))
                    #if (not os.path.isfile(fname)): #create only if it does not exist
                    if 1: # create every time, it is small and works over reconfigs
                        fd=open(fname,"w")
                        fd.write("<html>\n<head>\n")
                        fd.write("<title>%s over last %s</title>\n"%(client_name,period));
                        fd.write("</head>\n<body>\n")
                        fd.write("<h1>%s over last %s</h1>\n"%(client_name,period));
                        fd.write('<p>[<a href="0Status.%s.%s.html">Status</a>]</p>\n'%(period,size)) 
                        fd.write("<p>\n<table>\n")
                        for s in self.job_statuses:
                            if (not (s in ('Completed','Removed'))): # special treatement
                                fd.write('<tr valign="top">')
                                for w in ['Count','Diff']:
                                    fd.write('<td><img src="Log_%s_%s.%s.%s.png"></td>'%(s,w,period,size))
                                fd.write('</tr>\n')                            
                        fd.write("</table>\n</p>\n")
                        fd.write("<p>\n<h2>Terminated glideins</h2>\n<table>\n")
                        for s_arr in (('Diff','Entered_Lasted'),
                                      ('Entered_Waste_validation','Entered_Waste_idle'),
                                      ('Entered_Waste_nosuccess','Entered_Waste_badput')):
                            fd.write('<tr valign="top">')
                            for s in s_arr:
                                fd.write('<td><img src="Log_Completed_%s.%s.%s.png"></td>'%(s,period,size))
                            fd.write('</tr>\n')
                        
                        fd.write('<tr valign="top">')
                        fd.write('<td><img src="Log_Removed_Diff.%s.%s.png"></td>'%(period,size))
                        fd.write('</tr>\n')
                        fd.write("</table>\n</p>\n")

                        if client_name==None:
                            # total has also the split graphs
                            fd.write("<p><hr><p><table>")
                            for s in self.job_statuses:
                                if (not (s in ('Completed','Removed'))): # special treatement
                                    fd.write('<tr valign="top">')
                                    for w in ['Count','Diff']:
                                        fd.write('<td><img src="Split_Log_%s_%s.%s.%s.png"></td>'%(s,w,period,size))
                                    if s=='Running':
                                        fd.write('<td><img src="Split_Log_%s_%s.%s.%s.png"></td>'%('Completed','Diff',period,size))
                                    elif s=='Held':
                                        fd.write('<td><img src="Split_Log_%s_%s.%s.%s.png"></td>'%('Removed','Diff',period,size))
                                    fd.write('</tr>\n')                            
                            fd.write("</table>")
                            
                        fd.write("</body>\n</html>\n")
                        fd.close()
                        pass
                    pass # for sz
                pass # for rp
            pass # for client_name

        self.history_files_updated=self.files_updated
        return

############### P R I V A T E ################

def getUnitVal(u):
    if u=="TooShort":
        return 0
    if u=="m":
        return 1
    if u=="mins":
        return 2
    if u=="hours":
        return 3
    return 100 # just for protection

# compare (nr,unit) pairs
def cmpPairs(e1,e2):
    # first compare units
    u1=getUnitVal(e1[1])
    u2=getUnitVal(e2[1])
    ucmp=cmp(u1,u2)
    if ucmp!=0:
        return ucmp

    # units equal, compare numbers
    try:
        n1=int(e1[0])
    except:
        n1=10000
    try:
        n2=int(e2[0])
    except:
        n2=10000
    return cmp(n1,n2)


def tmp2final(fname):
    try:
        os.remove(fname+"~")
    except:
        pass

    try:
        os.rename(fname,fname+"~")
    except:
        pass

    try:
      os.rename(fname+".tmp",fname)
    except:
      print "Failed renaming %s.tmp into %s"%(fname,fname)
    return

def create_rrd(rrd_obj,rrdfname,
               rrd_step,rrd_archives,
               rrd_ds):
    start_time=(long(time.time()-1)/rrd_step)*rrd_step # make the start time to be aligned on the rrd_step boundary - needed for optimal resoultion selection 
    #print (rrdfname,start_time,rrd_step)+rrd_ds
    args=[str(rrdfname),'-b','%li'%start_time,'-s','%i'%rrd_step,'DS:%s:%s:%i:%s:%s'%rrd_ds]
    for archive in rrd_archives:
        args.append("RRA:%s:%g:%i:%i"%archive)

    rrd_obj.create(*args)
    return

def update_rrd(rrd_obj,rrdfname,
               time,val):
    rrd_obj.update(str(rrdfname),'%li:%i'%(time,val))
    return

#
# Deprecate for the moment, until we find a proper way
# to manage history XML files
#
#def rrd2xml(rrdbin,xmlfname,
#            rrd_step,ds_name,ds_type,
#            period,rrd_files):
#    now=long(time.time())
#    start=((now-period)/rrd_step)*rrd_step
#    end=((now-1)/rrd_step)*rrd_step
#    cmdline='%s xport -s %li -e %li --step %i' % (rrdbin,start,end,rrd_step)
#    for rrd_file in rrd_files:
#        cmdline=cmdline+" DEF:%s=%s:%s:%s"%(rrd_file+(ds_name,ds_type))
#
#    for rrd_file in rrd_files:
#        ds_id=rrd_file[0]
#        cmdline=cmdline+" XPORT:%s:%s"%(ds_id,ds_id)
#
#    cmdline=cmdline+" >%s"%xmlfname
#
#    #print cmdline
#    outstr=iexe_cmd(cmdline)
#    return

def rrd2graph(rrd_obj,fname,
              rrd_step,ds_name,ds_type,
              period,width,height,
              title,rrd_files):
    now=long(time.time())
    start=((now-period)/rrd_step)*rrd_step
    end=((now-1)/rrd_step)*rrd_step
    args=[str(fname),'-s','%li'%start,'-e','%li'%end,'--step','%i'%rrd_step,'-l','0','-w','%i'%width,'-h','%i'%height,'--imgformat','PNG','--title',str(title)]
    for rrd_file in rrd_files:
        ds_id=rrd_file[0]
        ds_fname=rrd_file[1]
        args.append(str("DEF:%s=%s:%s:%s"%(ds_id,ds_fname,ds_name,ds_type)))

    if rrd_files[0][2]=="STACK":
        # add an invisible baseline to stack upon
        args.append("AREA:0")
        
    for rrd_file in rrd_files:
        ds_id=rrd_file[0]
        ds_graph_type=rrd_file[2]
        ds_color=rrd_file[3]
        args.append("%s:%s#%s:%s"%(ds_graph_type,ds_id,ds_color,ds_id))

    args.append("COMMENT:Created on %s"%time.strftime("%b %d %H\:%M\:%S %Z %Y"))

    try:
      rrd_obj.graph(*args)
    except:
      print "Failed graph: %s"%str(args)
    return


###########################################################
#
# CVS info
#
# $Id: glideFactoryMonitoring.py,v 1.106 2008/05/20 16:28:31 sfiligoi Exp $
#
# Log:
#  $Log: glideFactoryMonitoring.py,v $
#  Revision 1.106  2008/05/20 16:28:31  sfiligoi
#  Properly calculate the InfoAge totals
#
#  Revision 1.105  2008/05/20 15:56:32  sfiligoi
#  Correct type
#
#  Revision 1.104  2008/05/20 15:33:45  sfiligoi
#  Comments
#
#  Revision 1.103  2008/05/11 19:59:36  sfiligoi
#  Add wait and pending
#
#  Revision 1.100  2008/05/11 17:50:50  sfiligoi
#  Add more text
#
#  Revision 1.98  2008/05/11 17:14:57  sfiligoi
#  Add client monitor info to the web page
#
#  Revision 1.97  2008/05/05 19:21:10  sfiligoi
#  Always re-create the index files to account for reconfigs
#
#  Revision 1.95  2007/12/18 18:08:28  sfiligoi
#  Better error handling
#
#  Revision 1.94  2007/10/12 16:16:31  sfiligoi
#  Add a 5% random distribution to the graph renewal
#
#  Revision 1.93  2007/10/12 16:09:34  sfiligoi
#  Reduce graph creation frequency
#
#  Revision 1.92  2007/10/12 14:48:11  sfiligoi
#  Get rid of the small rrds
#
#  Revision 1.91  2007/10/12 14:46:29  sfiligoi
#  Get rid of large images and rename medium to large
#
#  Revision 1.89  2007/10/10 20:03:57  sfiligoi
#  Better collors
#
#  Revision 1.88  2007/10/10 19:29:31  sfiligoi
#  Check for files before graphing
#
#  Revision 1.87  2007/10/10 19:26:50  sfiligoi
#  Check for files before graphing
#
#  Revision 1.86  2007/10/09 22:17:32  sfiligoi
#  Add title
#
#  Revision 1.84  2007/10/09 22:12:36  sfiligoi
#  Put new graphs into index file
#
#  Revision 1.82  2007/10/09 21:28:23  sfiligoi
#  Improve colors
#
#  Revision 1.81  2007/10/09 20:59:40  sfiligoi
#  Improve graphing
#
#  Revision 1.78  2007/10/09 20:05:55  sfiligoi
#  Improve stacking
#
#  Revision 1.75  2007/10/09 19:26:31  sfiligoi
#  Handle UINICODE properly
#
#  Revision 1.71  2007/10/09 18:38:00  sfiligoi
#  Add graph creation for lasted and waste
#
#  Revision 1.70  2007/10/09 15:25:57  sfiligoi
#  Protect from Condor-G latencies
#
#  Revision 1.69  2007/10/08 22:25:12  sfiligoi
#  Fix waste calculations
#
#  Revision 1.68  2007/10/08 19:30:55  sfiligoi
#  Change MillRange Log to be rounded on 1000
#
#  Revision 1.67  2007/10/08 19:25:55  sfiligoi
#  Change TimeRange Log to be rounded on the hour
#
#  Revision 1.61  2007/10/05 22:53:06  sfiligoi
#  Add ouptpu log parsing and waste reporting
#
#  Revision 1.60  2007/10/04 20:22:04  sfiligoi
#  Make time steps in multiples of 5
#
#  Revision 1.57  2007/10/04 18:58:22  sfiligoi
#  Use Timings
#
#  Revision 1.56  2007/09/26 21:53:36  sfiligoi
#  Strings
#
#  Revision 1.55  2007/09/26 21:37:07  sfiligoi
#  Prevent useless updates
#
#  Revision 1.54  2007/09/26 20:28:55  sfiligoi
#  Add protection from update problems
#
#  Revision 1.49  2007/09/26 19:33:06  sfiligoi
#  Use python-rrdtool if present
#
#  Revision 1.48  2007/07/03 19:46:19  sfiligoi
#  Add support for MaxRunningGlideins
#
#  Revision 1.47  2007/05/24 16:34:17  sfiligoi
#  Fix title in oLog and add a link to 0Status
#
#  Revision 1.46  2007/05/24 16:10:28  sfiligoi
#  Add links on all the -Sttaus files
#
#  Revision 1.45  2007/05/23 22:27:39  sfiligoi
#  Add week and year graphs
#
#  Revision 1.44  2007/05/23 22:04:14  sfiligoi
#  Create find_disk_attributes
#
#  Revision 1.43  2007/05/23 18:27:10  sfiligoi
#  Rename XML tag to glideFactoryEntryQStats... since it was moved one level higher in the directory structure
#
#  Revision 1.42  2007/05/23 17:55:44  sfiligoi
#  Add the missing Log for total monitoring
#
#  Revision 1.41  2007/05/23 16:26:52  sfiligoi
#  Add creation of Log rrds for total
#
#  Revision 1.40  2007/05/23 15:45:39  sfiligoi
#  Create graphs and XML files only when needed (before they were receated at each iteration, creating a huge load without any benefit)
#
#  Revision 1.39  2007/05/21 21:58:48  sfiligoi
#  Add a total page to the monitoring (still missing total log monitoring)
#
#  Revision 1.38  2007/05/21 17:06:12  sfiligoi
#  Add more exception handling
#
#  Revision 1.37  2007/05/18 19:10:57  sfiligoi
#  Add CVS tags
#
#
###########################################################
