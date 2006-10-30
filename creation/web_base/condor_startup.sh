#!/bin/bash

# This script starts the condor daemons
# expects a config file as a parameter


# pstr = variable representing an appendix
pstr='"'

config_file=$1

debug_mode=`grep -i "^DEBUG_MODE" $config_file | awk '{print $2}'`

if [ "$debug_mode" == "1" ]; then
    echo "-------- $config_file in condor_startup.sh ----------"
    cat $config_file
    echo "-----------------------------------------------------"
fi

export CONDOR_CONFIG="${PWD}/condor_config"

echo "# ---- start of condor_startup generated part ----" >> $CONDOR_CONFIG

# glidein_variables = list of additional variables startd is to publish
glidein_variables=""

# job_env = environment to pass to the job
job_env=""

#
# Set a variable read from a file
#
function set_var {
    var_name=$1
    var_type=$2
    var_def=$3
    var_condor=$4
    var_req=$5
    var_exportcondor=$6
    var_user=$7

    if [ -z "$var_name" ]; then
	# empty line
	return 0
    fi

    var_val=`grep "^$var_name" $config_file | awk '{idx=length($1); print substr($0,idx+2)}'`
    if [ -z "$var_val" ]; then
	if [ "$var_req" == "Y" ]; then
	    # needed var, exit with error
	    echo "Cannot extract $var_name from '$config_file'" 1>&2
	    exit 1
	elif [ "$var_def" == "-" ]; then
	    # no default, do not set
	    return 0
	else
	    eval var_val=$var_def
	fi
    fi
    
    if [ "$var_condor" == "+" ]; then
	var_condor=$var_name
    fi
    if [ "$var_type" == "S" ]; then
	var_val_str="${pstr}${var_val}${pstr}"
    else
	var_val_str="$var_val"
    fi

    # insert into condor_config
    echo "$var_condor=$var_val_str" >> $CONDOR_CONFIG

    if [ "$var_exportcondor" == "Y" ]; then
	# register var_condor for export
	if [ -z "$glidein_variables" ]; then
	   glidein_variables="$var_condor"
	else
	   glidein_variables="$glidein_variables,$var_condor"
	fi
    fi

    if [ "$var_user" != "-" ]; then
	# - means do not export
	if [ "$var_user" == "+" ]; then
	    var_user=$var_name
	elif [ "$var_user" == "@" ]; then
	    var_user=$var_condor
	fi

	if [ -z "$job_env" ]; then
	   job_env="$var_user=$var_val"
	else
	   job_env="$job_env;$var_user=$var_val"
	fi
    fi

    # define it for future use
    eval "$var_name='$var_val'"
    return 0
}

grep -v "^#" condor_vars.lst > condor_vars.lst.tmp 
while read line
do
    set_var $line
done < condor_vars.lst.tmp

#let "max_job_time=$job_max_hours * 3600"

#now=`date +%s`
#let "max_proxy_time=$X509_EXPIRE - $now - 1"

#if [ $max_proxy_time -lt $max_job_time ]; then
#    max_job_time=$max_proxy_time
#    glidein_expire=$x509_expire
#else
#    let "glidein_expire=$now + $max_job_time"
#fi

#let "glidein_toretire=$now + $glidein_retire_time"

cat >> "$CONDOR_CONFIG" <<EOF
# ---- start of condor_startup fixed part ----

LOCAL_DIR = $PWD

#GLIDEIN_EXPIRE = $glidein_expire
#GLIDEIN_TORETIRE = $glidein_toretire

STARTER_JOB_ENVIRONMENT = $job_env
GLIDEIN_VARIABLES = $glidein_variables

MASTER_NAME = ${GLIDEIN_Site}_$$

EOF
# ##################################
if [ $? -ne 0 ]; then
    echo "Error customizing the condor_config" 1>&2
    exit 1
fi

if [ "$debug_mode" == "1" ]; then
  echo "--- condor_config ---"
  cat $CONDOR_CONFIG
  echo "--- ============= ---"
  env
  echo "--- ============= ---"
  echo
  #env
fi

echo === Condor starting `date` ===

let "retmins=$GLIDEIN_Retire_Time / 60 - 1"
$CONDOR_DIR/condor_master -r $retmins -dyn -f 
ret=$?

echo === Condor ended `date` ===
echo

if [ "$debug_mode" == "1" ]; then
    ls -l log*/*
    echo "MasterLog"
    echo "=================================================="
    tail -100 log*/MasterLog
    echo "--------------------------------------------------"
    echo
    echo "StartdLog"
    echo "=================================================="
    tail -100 log*/StartdLog
    echo "--------------------------------------------------"
    echo
    echo "StarterLog.vm2"
    echo "=================================================="
    tail -100 log*/StarterLog.vm2
    echo "--------------------------------------------------"
    echo
    echo "StarterLog.vm1"
    echo "=================================================="
    tail -100 log*/StarterLog.vm1
    echo "--------------------------------------------------"
    echo
fi

exit $ret
