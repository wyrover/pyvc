import sys
import os
import json
import hashlib
import re
import subprocess
import xml.etree.ElementTree as ET
import cPickle


def add_path(path, filename):
    if path[len(path) - 1] == '\\':
        return path + filename
    return path + '\\' + filename


class TProject:

    def __init__(self):
        incDirs = []
        libDirs = ''
        libs = ''
        preDefines = ''
        outFile = ''
        outDir = ''
        srcfiles = []


def parse_vcproj(vcproj_file, config_name):
    f = file(vcproj_file, 'r')
    lines = f.readlines()
    f.close()

    data = ''
    try:
        if lines[0].find('"gb2312"'):
            lines[0] = lines[0].replace('"gb2312"', '"utf-8"')
            data = ''.join(lines)
            data = data.decode('gb2312').encode('utf-8')
    except:
        bb
        data = ''.join(lines)

    root = ET.fromstring(data)

    project = TProject()
    if 'Name' in root.attrib:
        project.proj_name = root.attrib['Name']
    project.filename = os.path.realpath(vcproj_file)
    project.proj_dir = os.path.dirname(project.filename)

    incDirs = []
    outFile = ''
    outFileType = ''
    libDirs = []
    project.depends = []
    for config in root.iter('Configuration'):
        if config.attrib['Name'].lower() != config_name.lower():
            continue
        if config.attrib['ConfigurationType'] == '1':
            outFileType = '.exe'
        elif config.attrib['ConfigurationType'] == '2':
            outFileType = '.dll'
        elif config.attrib['ConfigurationType'] == '4':
            outFileType = '.lib'
        else:
            break

        if 'CharacterSet' in config.attrib and config.attrib['CharacterSet'] == '1':
            project.charset = 'unicode'
        else:
            project.charset = ''

        for tool in config.iter('Tool'):
            if tool.attrib['Name'] == 'VCCLCompilerTool':
                if 'AdditionalIncludeDirectories' in tool.attrib:
                    incDirs = tool.attrib[
                        'AdditionalIncludeDirectories'].split(';')
            if tool.attrib['Name'] == 'VCLibrarianTool':
                if 'OutputFile' in tool.attrib:
                    outFile = tool.attrib['OutputFile']
            if tool.attrib['Name'] == 'VCLinkerTool':
                if 'OutputFile' in tool.attrib:
                    outFile = tool.attrib['OutputFile']
                if 'AdditionalLibraryDirectories' in tool.attrib:
                    libDirs = tool.attrib[
                        'AdditionalLibraryDirectories'].split(';')
                if 'AdditionalDependencies' in tool.attrib:
                    project.depends = tool.attrib[
                        'AdditionalDependencies'].split(' ')

    if outFileType == '':
        return project

    if outFile == '':
        outFile = project.proj_name + outFileType
    else:
        outFile = outFile.replace('$(ProjectName)', project.proj_name)

    outFileList = os.path.splitext(outFile)
    project.outBasename = os.path.basename(outFileList[0])
    project.ext = outFileList[1].lower()

    project.outFile = os.path.basename(outFile)

    srcfiles = []
    for f in root.iter('File'):
        srcfile = f.attrib['RelativePath']
        srcfiles.append(srcfile)

    project.incDirs = [add_path(project.proj_dir, incdir)
                       for incdir in incDirs]
    project.libDirs = [add_path(project.proj_dir, libdir)
                       for libdir in libDirs]
    project.srcfiles = [add_path(project.proj_dir, filename)
                        for filename in srcfiles]
    return project

CL = 'cl.exe /DWIN32 /DNDEBUG /D_WINDOWS /D_CRT_SECURE_NO_DEPRECATE /DLOG4CPLUS_BUILD_DLL /DINSIDE_LOG4CPLUS /D_SECURE_SCL_THROWS=1 /DENABLE_XP /DLUAJIT_ENABLE_LUA52COMPAT /DLUAJIT_DISABLE_JIT /DLUA_BUILD_AS_DLL /D_RAKNET_LIB /DLUASNAPSHOT_EXPORTS /DLUAPROFILER_EXPORTS /DUSE_INTERNAL_ISINF /DUSE_INTERNAL_FPCONV /DMONGO_EXPOSE_MACROS /DLUAMONGO_EXPORTS /DAMQP_BUILD /Drabbitmq_EXPORTS /DHAVE_CONFIG_H /O2 /GF /EHsc /MD /MP /Oy- /W4 /Zi /nologo /wd4512 /wd4100 /wd4996 /wd4244 /wd4127 /wd4125 /wd4702 /wd4201 /c'.split(
    ' ')


def compile_src(srcfiles, incDirs, tmpdir, options):
    argv = CL + incDirs + options + ['/Fo' + tmpdir] + srcfiles
    #print('cl', argv)
    return subprocess.call(argv)

LIB = 'lib.exe /NOLOGO'.split(' ')


def lib(outFile, objects, options):
    argv = LIB + options + ['/OUT:' + outFile] + objects
    #print('lib', ' '.join(argv))
    return subprocess.call(argv)

LINK = 'link.exe /OPT:REF /OPT:ICF /DEBUG /MAP /NOLOGO'.split(' ')

libs = 'msvcrt.lib kernel32.lib user32.lib gdi32.lib winspool.lib comdlg32.lib advapi32.lib shell32.lib ole32.lib oleaut32.lib uuid.lib odbc32.lib odbccp32.lib'.split(
    ' ')


def link(outFile, objects, libDirs, libs, options):
    argv = LINK + options + libDirs + ['/OUT:' + outFile] + objects + libs
    #print('link', argv)
    return subprocess.call(argv)

tempbasedir = 'D:\\build_temp\\'
cache = {}


def is_file_changed(cache, filename):
    if filename in cache:
        mtime = os.path.getmtime(filename)
        if cache[filename]['mtime'] == mtime:
            return False
        else:
            f = file(filename, 'rb')
            data = f.read()
            f.close()
            sha1 = hashlib.sha1(data).hexdigest()
            if cache[filename]['sha1'] == sha1:
                print(filename, sha1)
                cache['mtime'] = mtime
                return False
    return True


def update_cache(cache, filename):
    if filename in cache:
        pass
    else:
        cache[filename] = {}

    cache[filename]['mtime'] = os.path.getmtime(filename)
    f = file(filename, 'rb')
    data = f.read()
    f.close()
    cache[filename]['sha1'] = hashlib.sha1(data).hexdigest()

local_header_pattern = re.compile('\s*#include\s+"(.+)"')
system_header_pattern = re.compile('\s*#include\s+<(.+)>')
depends = {}


def parse_c_depends(filename, changed, incDirs):
    # if changed == False:
    #       if filename in depends:
    #               return depends[filename]
    #       else:
    #               return []

    local_depends, system_depends = [], []
    f = file(filename, 'r')
    for line in f:
        r = re.search(local_header_pattern, line)
        if r is not None:
            local_depends.append(r.group(1))
        r = re.search(system_header_pattern, line)
        if r is not None:
            system_depends.append(r.group(1))

    f.close()

    print(filename, local_depends, system_depends)

    file_depends = []

    def check_and_append(depends, file_path):
        if os.path.exists(file_path):
            depends.append(file_path)
            update_cache(cache, file_path)
            return True
        return False

    file_dir = os.path.dirname(filename) + '\\'
    for local in local_depends:
        depend_path = file_dir + local
        check_and_append(file_depends, depend_path)

    for system in system_depends:
        for incDir in incDirs:
            depend_path = incDir + system
            if os.path.exists(depend_path):
                file_depends.append(depend_path)
                break

    depends[filename] = file_depends
    return file_depends


def build_vcproj(vcproj_file, config_name):
    project = parse_vcproj(vcproj_file, config_name)

    tempdir = tempbasedir + project.proj_name + '\\'
    if not os.path.exists(tempdir):
        os.makedirs(tempdir)

    proj_file_changed = is_file_changed(cache, project.filename)
    update_cache(cache, project.filename)
    save_cache(cache, cacheFileName)
    success = True
    changed = False
    objects = []

    srcfiles = []
    for f in project.srcfiles:
        fl = os.path.splitext(f)
        ext = fl[1].lower()
        if ext in ['.c', '.cpp', '.cxx', '.cc']:
            if not os.path.exists(f):
                raise Exception(f, 'not exist')

            src_changed = is_file_changed(cache, f)
            if (not proj_file_changed) and (not src_changed) and os.path.exists(cache[f]['obj']):
                need_compile = False
                depends = parse_c_depends(f, src_changed, project.incDirs)
                print(depends)
                for depend in depends:
                    if is_file_changed(cache, depend):
                        need_compile = True
                        break

                if need_compile is False:
                    objects.append(cache[f]['obj'])
                    continue

            srcfiles.append(f)
            changed = True

        elif ext in ['.obj']:
            if not os.path.exists(f):
                raise Exception(f, 'not exist')
            objects.append(f)
        elif ext in ['.def']:
            if not os.path.exists(f):
                raise Exception(f, 'not exist')
            objects.append('/DEF:' + f)
        elif ext == '.rc':
            pass

    if len(srcfiles) > 0:
        cl_options = []
        if project.ext == '.lib':
            cl_options.append('/D_LIB')
        elif project.ext == '.dll':
            cl_options.append('/D_WINDLL')
            cl_options.append('/D_USRDLL')

        if project.charset == 'unicode':
            cl_options.append('/D_UNICODE')
            cl_options.append('/DUNICODE')

        incparams = []
        for incdir in project.incDirs:
            incparams.append('/I')
            incparams.append(incdir)

        if compile_src(srcfiles, incparams, tempdir, cl_options) == 0:
            for filename in srcfiles:
                fl = os.path.splitext(filename)
                update_cache(cache, filename)
                basename = os.path.basename(fl[0]).lower()
                cache[filename]['obj'] = tempdir + basename + '.obj'
                objects.append(tempdir + basename + '.obj')
            save_cache(cache, cacheFileName)
        else:
            raise Exception("BUILD_FAILED", vcproj_file)

    outPath = tempbasedir + project.outFile
    if (not os.path.exists(outPath)) or changed:
        options = []
        if project.ext == '.lib':
            if lib(outPath, objects, options) != 0:
                raise Exception("LIB_FAILED", vcproj_file)
        else:
            if project.ext == '.dll':
                options.append('/DLL')
            libparams = []
            for libdir in project.libDirs + [tempbasedir]:
                libparams.append('/LIBPATH:' + libdir)
            if link(outPath, objects, libparams, project.depends + libs, options) != 0:
                raise Exception("LINK_FAILED", vcproj_file)
    if project.ext in ['.lib', '.dll']:
        libs.append(tempbasedir + project.outBasename + '.lib')


def load_cache(filename):
    cache = {}
    if os.path.exists(filename):
        cacheFile = file(filename, 'r')
        cache = cPickle.load(cacheFile)
        cacheFile.close()

    return cache


def save_cache(cache, outFile):
    cacheFile = file(outFile, 'w')
    cPickle.dump(cache, cacheFile)
    cacheFile.close()

if __name__ == '__main__':
    relativepath = os.path.dirname(os.path.realpath(__file__)) + '\\..\\'
    if len(sys.argv) > 1:
        tempbasedir = sys.argv[1]

    cacheFileName = tempbasedir + '.cache'
    cache = load_cache(cacheFileName)

    # try:
    build_vcproj(
        relativepath + 'code\\contrib\\hpf\\hpf\\hpf.vcproj', 'Release|Win32')
    # build_vcproj(
    #     relativepath + 'code\\contrib\\log4cplus\\log4cplus\\msvc8\\log4cplus_dll.vcproj', 'Release|Win32')
    # build_vcproj(
    #     relativepath + 'code\\contrib\\lua\\lua51\\lua51.vcproj', 'Release-dll|win32')
    # build_vcproj(
    #     relativepath + 'code\\contrib\\luaprofiler\\luaprofiler.vcproj', 'Release-dll|win32')
    # build_vcproj(
    #     relativepath + 'code\\contrib\\lua-snapshot\\lua-snapshot.vcproj', 'Release-dll|win32')
    # build_vcproj(
    #     relativepath + 'code\\contrib\\luajson\\luajson\\luajson.vcproj', 'Release-dll|win32')
    # build_vcproj(
    #     relativepath + 'code\\contrib\\lz4\\lz4.vcproj', 'Release|win32')
    # build_vcproj(
    #     relativepath + 'code\\contrib\\loki\\loki-0.1.7\\src\\library.vcproj', 'Release|win32')
    # build_vcproj(
    #     relativepath + 'code\\contrib\\protobuf\\vsprojects\\libprotobuf.vcproj', 'Release|win32')
    # build_vcproj(
    #     relativepath + 'code\\contrib\\scgl\\scgl.vcproj', 'Release|win32')
    # build_vcproj('code\\contrib\\raknet\\raknet-4.0\\lib\\libstatic\\libstatic_vc8.vcproj', 'Release|win32')
    # build_vcproj('code\\contrib\\mongo\\mongoclient\\mongoclient.vcproj', 'Release-dll|win32')
    # build_vcproj('code\\contrib\\luamongo\\luamongo.vcproj', 'Release-dll|win32')
    # build_vcproj('code\\contrib\\rabbitmq\\build\\librabbitmq\\rabbitmq.vcproj', 'Release|win32')
    # build_vcproj('code\\Server\\AvatarServer\\server\\server.vcproj', 'Release|Win32')
