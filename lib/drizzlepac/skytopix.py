""" skytopix - A module to perform coordinate transformation from sky
    to pixel coordinates.

    :Authors: Warren Hack

    :License: `<http://www.stsci.edu/resources/software_hardware/pyraf/LICENSE>`_

    PARAMETERS
    ----------
    input : str
        full filename with path of input image, an extension name
        ['sci',1] should be provided if input is a multi-extension
        FITS file

    Optional Parameters
    -------------------
    ra : string or list or array, optional
        RA from input image for a single or multiple positions
    dec : string or list or array, optional
        Dec from input image for a single or multiple positions
    coordfile : str, optional
        full filename with path of file with sky coordinates
    colnames : str, optional
        comma separated list of column names or list of column name strings
        from 'coordfile' files containing x,y coordinates, respectively.
        This parameter will default to first two columns if None are specified.
        Column names for ASCII files will use 'c1','c2',... convention.
        Valid syntax: ['c1','c3'] or 'c1,c3'
    separator : str, optional
        non-blank separator used as the column delimiter in the coords file
    precision : int, optional
        Number of floating-point digits in output values
    output : str, optional
        Name of output file with results, if desired
    verbose : bool
        Print out full list of transformation results (default: False)

    RETURNS
    -------
    x : float or array
        X position of pixel. If more than 1 input value, then it will be a
        numpy array.
    y : float or array
        Y position of pixel. If more than 1 input value, then it will be a
        numpy array.


    NOTES
    -----
    This module performs a full distortion-corrected coordinate
    transformation based on all WCS keywords and any recognized
    distortion keywords from the input image header.


    EXAMPLES
    --------
    1. The following command will transform the position 00:22:36.79 -72:4:9.0 into a
       position on the image 'input_flt.fits[sci,1]' using::

            >>> from drizzlepac import skytopix
            >>> x,y = skytopix.rd2xy("input_file_flt.fits[sci,1]", "00:22:36.79","-72:4:9.0")


    2. The set of sky positions from 'input_flt.fits[sci,1]' stored as
       the 3rd and 4th columns from the ASCII file 'radec_sci1.dat'
       will be transformed and written out to 'xy_sci1.dat' using::

            >>> from drizzlepac import skytopix
            >>> x,y = skytopix.rd2xy("input_flt.fits[sci,1]", coordfile='radec_sci1.dat',
                colnames=['c3','c4'], output="xy_sci1.dat")

"""
from __future__ import absolute_import, division, print_function # confidence medium

import os,copy
import numpy as np

from astropy.io import fits
from stsci.tools import fileutil, teal
from . import util,wcs_functions,tweakutils
import stwcs
from stwcs import distortion,wcsutil

# This is specifically NOT intended to match the package-wide version information.
__version__ = '0.1'
__vdate__ = '25-Feb-2011'

__taskname__ = 'skytopix'

blank_list = [None, '', ' ']

def rd2xy(input,ra=None,dec=None,coordfile=None,colnames=None,
            precision=6,output=None,verbose=True):
    """ Primary interface to perform coordinate transformations from
        pixel to sky coordinates using STWCS and full distortion models
        read from the input image header.
    """
    single_coord = False
    if coordfile is not None:
        if colnames in blank_list:
            colnames = ['c1','c2']
        elif isinstance(colnames,type('a')):
            colnames = colnames.split(',')
        # convert input file coordinates to lists of decimal degrees values
        xlist,ylist = tweakutils.readcols(coordfile,cols=colnames)
    else:
        if isinstance(ra,np.ndarray):
            ralist = ra.tolist()
            declist = dec.tolist()
        elif not isinstance(ra, list):
            ralist = [ra]
            declist = [dec]
        else:
            ralist = ra
            declist = dec
        xlist  = [0]*len(ralist)
        ylist = [0]*len(ralist)
        if len(xlist) == 1:
            single_coord = True
        for i,(r,d) in enumerate(zip(ralist,declist)):
            # convert input value into decimal degrees value
            xval,yval = tweakutils.parse_skypos(r,d)
            xlist[i] = xval
            ylist[i] = yval

    # start by reading in WCS+distortion info for input image
    inwcs = wcsutil.HSTWCS(input)
    if inwcs.wcs.is_unity():
        print("####\nNo valid WCS found in {}.\n  Results may be invalid.\n####\n".format(input))

    # Now, convert pixel coordinates into sky coordinates
    try:
        outx,outy = inwcs.all_world2pix(xlist,ylist,1)
    except RuntimeError:
        outx,outy = inwcs.wcs_world2pix(xlist,ylist,1)

    # add formatting based on precision here...
    xstr = []
    ystr = []
    fmt = "%."+repr(precision)+"f"
    for x,y in zip(outx,outy):
        xstr.append(fmt%x)
        ystr.append(fmt%y)

    if verbose or (not verbose and util.is_blank(output)):
        print ('# Coordinate transformations for ',input)
        print('# X      Y         RA             Dec\n')
        for x,y,r,d in zip(xstr,ystr,xlist,ylist):
            print("%s  %s    %s  %s"%(x,y,r,d))

    # Create output file, if specified
    if output:
        f = open(output,mode='w')
        f.write("# Coordinates converted from %s\n"%input)
        for x,y in zip(xstr,ystr):
            f.write('%s    %s\n'%(x,y))
        f.close()
        print('Wrote out results to: ',output)

    if single_coord:
        outx = outx[0]
        outy = outy[0]
    return outx,outy

    """ Convert colnames input into list of column numbers
    """
    cols = []
    if not isinstance(colnames,list):
        colnames = colnames.split(',')

    # parse column names from coords file and match to input values
    if coordfile is not None and fileutil.isFits(coordfile)[0]:
        # Open FITS file with table
        ftab = fits.open(coordfile)
        # determine which extension has the table
        for extn in ftab:
            if isinstance(extn, fits.BinTableHDU):
                # parse column names from table and match to inputs
                cnames = extn.columns.names
                if colnames is not None:
                    for c in colnames:
                        for name,i in zip(cnames,list(range(len(cnames)))):
                            if c == name.lower(): cols.append(i)
                    if len(cols) < len(colnames):
                        errmsg = "Not all input columns found in table..."
                        ftab.close()
                        raise ValueError(errmsg)
                else:
                    cols = cnames[:2]
                break
        ftab.close()
    else:
        for c in colnames:
            if isinstance(c, str):
                if c[0].lower() == 'c':
                    cols.append(int(c[1:])-1)
                else:
                    cols.append(int(c))
            else:
                if isinstance(c, int):
                    cols.append(c)
                else:
                    errmsg = "Unsupported column names..."
                    raise ValueError(errmsg)
    return cols


#--------------------------
# TEAL Interface functions
#--------------------------
def run(configObj):

    coordfile = util.check_blank(configObj['coordfile'])
    colnames = util.check_blank(configObj['colnames'])
    outfile = util.check_blank(configObj['output'])

    rd2xy(configObj['input'],
            ra = configObj['ra'], dec = configObj['dec'],
            coordfile = coordfile, colnames = colnames,
            precision= configObj['precision'],
            output= outfile, verbose = configObj['verbose'])


def help(file=None):
    """
    Print out syntax help for running astrodrizzle

    Parameters
    ----------
    file : str (Default = None)
        If given, write out help to the filename specified by this parameter
        Any previously existing file with this name will be deleted before
        writing out the help.

    """
    helpstr = getHelpAsString(docstring=True, show_ver = True)
    if file is None:
        print(helpstr)
    else:
        if os.path.exists(file): os.remove(file)
        f = open(file, mode = 'w')
        f.write(helpstr)
        f.close()


def getHelpAsString(docstring = False, show_ver = True):
    """
    return useful help from a file in the script directory called
    __taskname__.help

    """
    install_dir = os.path.dirname(__file__)
    taskname = util.base_taskname(__taskname__, '')
    htmlfile = os.path.join(install_dir, 'htmlhelp', taskname + '.html')
    helpfile = os.path.join(install_dir, taskname + '.help')

    if docstring or (not docstring and not os.path.exists(htmlfile)):
        if show_ver:
            helpString = os.linesep + \
                ' '.join([__taskname__, 'Version', __version__,
                ' updated on ', __vdate__]) + 2*os.linesep
        else:
            helpString = ''
        if os.path.exists(helpfile):
            helpString += teal.getHelpFileAsString(taskname, __file__)
        else:
            if __doc__ is not None:
                helpString += __doc__ + os.linesep
    else:
        helpString = 'file://' + htmlfile

    return helpString

__doc__ = getHelpAsString(docstring = True, show_ver = False)
