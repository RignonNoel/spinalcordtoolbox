#!/usr/bin/env python
#########################################################################################
#
# Visualizer for MRI volumes
#
#
# ---------------------------------------------------------------------------------------
# Copyright (c) 2015 Polytechnique Montreal <www.neuro.polymtl.ca>
# Authors: Benjamin De Leener
# Created: 2015-01-30
# Modified: 2016-02-26
#
# About the license: see the file LICENSE.TXT
#########################################################################################
import sys
from msct_parser import Parser
from msct_image import Image
from bisect import bisect
from numpy import arange, min
from msct_types import *
import matplotlib.pyplot as plt


# from matplotlib.widgets import Slider, Button, RadioButtons

class SinglePlot:
    """
        This class manages mouse events on one image.
    """
    def __init__(self, fig, volume, viewer, number_of_slices=0, gap_inter_slice=0):
        self.fig = fig
        self.volume = volume
        self.viewer = viewer

        self.image_dim = self.volume.data.shape

        self.list_points = []
        self.list_points_useful_notation = ''

        self.list_slices = []

        self.number_of_slices = number_of_slices
        self.gap_inter_slice = gap_inter_slice
        if self.number_of_slices != 0 and self.gap_inter_slice != 0:  # mode multiple points with fixed gap
            central_slice = int(self.image_dim[1]/2)
            first_slice = central_slice - (self.number_of_slices / 2) * self.gap_inter_slice
            last_slice = central_slice + (self.number_of_slices / 2) * self.gap_inter_slice
            self.list_slices = list(range(first_slice, last_slice, self.number_of_slices))
        elif self.number_of_slices != 0:
            self.list_slices = list(range(0, self.image_dim[1], self.number_of_slices))
        elif self.gap_inter_slice != 0:
            self.list_slices = list(arange(0, self.image_dim[1], self.gap_inter_slice))
        else:
            self.number_of_slices = int(self.image_dim[1] / 10)
            self.list_slices = list(range(0, self.image_dim[1], self.number_of_slices))

        if self.list_slices[-1] != self.image_dim[1]-1:
            self.list_slices.append(self.image_dim[1]-1)
        self.current_slice = 0

        # variable to check if all slices have been processed
        self.all_processed = False

        # zoom variables
        self.zoom_factor = 0

    def connect(self):
        """
        connect to all the events we need
        :return:
        """
        self.fig.set_data(self.volume.data[:, int(self.list_slices[self.current_slice]), :])
        self.cidpress_click = self.fig.figure.canvas.mpl_connect('button_press_event', self.on_press)
        self.cidpress_scroll = self.fig.figure.canvas.mpl_connect('scroll_event', self.on_scroll)

    def draw(self):
        self.fig.figure.canvas.draw()

    def updateSlice(self, target_slice):
        """
        This function change the viewer to update the current slice
        :param slice: number of the slice to go on
        :return:
        """
        if 0 <= slice < self.image_dim[1]:
            self.fig.set_data(self.volume.data[:, target_slice, :])
            self.current_slice = bisect(self.list_slices, target_slice)
            self.fig.figure.canvas.draw()

    def on_press(self, event):
        """
        when pressing on the screen, add point into a list, then change current slice
        if finished, close the window and send the result
        :param event:
        :return:
        """
        if event.button == 1:
            self.list_points.append(Coordinate([int(event.ydata), int(self.list_slices[self.current_slice]), int(event.xdata), 1]))

            self.current_slice += 1
            if self.current_slice < len(self.list_slices):
                self.fig.set_data(self.volume.data[:, self.list_slices[self.current_slice], :])
                self.fig.figure.canvas.draw()
                self.viewer.update_current_slice(self.list_slices[self.current_slice])
            else:
                for coord in self.list_points:
                    #print 'Position=(' + str(coord.x) + ',' + str(coord.y) + ',' + str(coord.z) + ') -- Value= ' + str(coord.value)
                    if self.list_points_useful_notation != '':
                        self.list_points_useful_notation = self.list_points_useful_notation + ':'
                    self.list_points_useful_notation = self.list_points_useful_notation + str(coord.x) + ',' + str(coord.y) + ',' + str(coord.z) + ',' + str(coord.value)
                self.all_processed = True
                plt.close()

        return

    def on_scroll(self, event):
        """
        when scrooling with the wheel, image is zoomed toward position on the screen
        :param event:
        :return:
        """
        base_scale = 2.
        xdata, ydata = event.xdata, event.ydata

        # get the current x and y limits
        cur_xlim = self.fig.axes.get_xlim()
        cur_ylim = self.fig.axes.get_ylim()

        # Get distance from the cursor to the edge of the figure frame
        x_left = xdata - cur_xlim[0]
        x_right = cur_xlim[1] - xdata
        y_top = ydata - cur_ylim[0]
        y_bottom = cur_ylim[1] - ydata

        if event.button == 'down':
            # deal with zoom in
            scale_factor = 1 / base_scale
        elif event.button == 'up':
            # deal with zoom out
            scale_factor = base_scale
        else:
            # deal with something that should never happen
            scale_factor = 1
            print event.button

        print '\n'
        #print self.zoom_factor, [self.image_dim[2], self.image_dim[0]], mouse_x, mouse_y
        #print mouse_x - (self.image_dim[2] - self.zoom_factor), mouse_x + (self.image_dim[2] - self.zoom_factor), mouse_y - (self.image_dim[0] - self.zoom_factor), mouse_y + (self.image_dim[0] - self.zoom_factor)
        print [xdata - x_left * scale_factor, xdata + x_right * scale_factor], [ydata - y_top * scale_factor, ydata + y_bottom * scale_factor]
        self.fig.axes.set_xlim([xdata - x_left * scale_factor, xdata + x_right * scale_factor])
        self.fig.axes.set_ylim([ydata - y_top * scale_factor, ydata + y_bottom * scale_factor])
        #self.fig.axes.set_xlim(mouse_x - (self.image_dim[2] - self.zoom_factor), mouse_x + (self.image_dim[2] - self.zoom_factor))
        #self.fig.axes.set_ylim(mouse_y - (self.image_dim[0] - self.zoom_factor), mouse_y + (self.image_dim[0] - self.zoom_factor))
        self.fig.figure.canvas.draw()

        return


class ClickViewer(object):
    """
    This class is a visualizer for volumes (3D images) and ask user to click on axial slices.
    """
    def __init__(self, image):
        if isinstance(image, Image):
            self.image = image
        else:
            print "Error, the image is actually not an image"
        self.current_slice = 0
        self.window = None
        self.number_of_slices = 0
        self.gap_inter_slice = 0

    def update_current_slice(self, current_slice):
        self.current_slice = current_slice

    def get_results(self):
        if self.window:
            return self.window.list_points
        else:
            return None

    def start(self):
        self.fig = plt.figure()
        self.fig.subplots_adjust(bottom=0.1, left=0.1)

        self.im_size = self.image.data.shape

        ax = self.fig.add_subplot(111)
        self.im_plot_axial = ax.imshow(self.image.data[:, int(self.im_size[1] / 2), :])
        self.im_plot_axial.set_cmap('gray')
        self.im_plot_axial.set_interpolation('nearest')

        self.window = SinglePlot(self.im_plot_axial, self.image, self, self.number_of_slices, self.gap_inter_slice)
        self.window.connect()

        plt.show()

        if self.window.all_processed:
            return self.window.list_points_useful_notation
        else:
            return None


class TrioPlot:
    """
    This class manages mouse events on the three image subplots.
    """
    def __init__(self, fig_axial, fig_frontal, fig_sagittal, volume):
        self.fig_axial = fig_axial
        self.fig_frontal = fig_frontal
        self.fig_sagittal = fig_sagittal
        self.volume = volume

    def connect(self):
        """
        connect to all the events we need
        :return:
        """
        self.cidpress = self.fig_axial.figure.canvas.mpl_connect('button_press_event', self.on_press)
        self.cidrelease = self.fig_axial.figure.canvas.mpl_connect('button_release_event', self.on_release)
        self.cidmotion = self.fig_axial.figure.canvas.mpl_connect('motion_notify_event', self.on_motion)

        self.cidpress = self.fig_frontal.figure.canvas.mpl_connect('button_press_event', self.on_press)
        self.cidrelease = self.fig_frontal.figure.canvas.mpl_connect('button_release_event', self.on_release)
        self.cidmotion = self.fig_frontal.figure.canvas.mpl_connect('motion_notify_event', self.on_motion)

        self.cidpress = self.fig_sagittal.figure.canvas.mpl_connect('button_press_event', self.on_press)
        self.cidrelease = self.fig_sagittal.figure.canvas.mpl_connect('button_release_event', self.on_release)
        self.cidmotion = self.fig_sagittal.figure.canvas.mpl_connect('motion_notify_event', self.on_motion)

    def on_press(self, event):
        self.press = event.xdata, event.ydata
        return

    def draw(self):
        self.fig_axial.figure.canvas.draw()
        self.fig_frontal.figure.canvas.draw()
        self.fig_sagittal.figure.canvas.draw()

    def move(self, event):
        if event.xdata and abs(event.xdata-self.press[0])<1 and abs(event.ydata-self.press[0])<1:
            self.press = event.xdata, event.ydata
            return

        if event.inaxes == self.fig_axial.axes:
            self.fig_frontal.set_data(self.volume.data[event.ydata,:,:])
            self.fig_sagittal.set_data(self.volume.data[:,:,event.xdata])

            self.fig_frontal.figure.canvas.draw()
            self.fig_sagittal.figure.canvas.draw()

            self.press = event.xdata, event.ydata
            return

        elif event.inaxes == self.fig_frontal.axes:
            self.fig_axial.set_data(self.volume.data[:,event.ydata,:])
            self.fig_sagittal.set_data(self.volume.data[:,:,event.xdata])

            self.fig_axial.figure.canvas.draw()
            self.fig_sagittal.figure.canvas.draw()

            self.press = event.xdata, event.ydata
            return

        elif event.inaxes == self.fig_sagittal.axes:
            self.fig_axial.set_data(self.volume.data[:,event.xdata,:])
            self.fig_frontal.set_data(self.volume.data[event.ydata,:,:])

            self.fig_axial.figure.canvas.draw()
            self.fig_frontal.figure.canvas.draw()

            self.press = event.xdata, event.ydata
            return

        else: return

    def on_motion(self, event):
        if event.button == 1:
            return self.move(event)
        else:
            return


    def on_release(self, event):
        if event.button == 1:
            return self.move(event)
        else:
            return

    def disconnect(self):
        'disconnect all the stored connection ids'
        self.fig_axial.figure.canvas.mpl_disconnect(self.cidpress)
        self.fig_axial.figure.canvas.mpl_disconnect(self.cidrelease)
        self.fig_axial.figure.canvas.mpl_disconnect(self.cidmotion)

        self.fig_frontal.figure.canvas.mpl_disconnect(self.cidpress)
        self.fig_frontal.figure.canvas.mpl_disconnect(self.cidrelease)
        self.fig_frontal.figure.canvas.mpl_disconnect(self.cidmotion)

        self.fig_sagittal.figure.canvas.mpl_disconnect(self.cidpress)
        self.fig_sagittal.figure.canvas.mpl_disconnect(self.cidrelease)
        self.fig_sagittal.figure.canvas.mpl_disconnect(self.cidmotion)

class VolViewer(object):
    """
    This class is a visualizer for volumes (3D images).
    """
    def __init__(self,image):
        if isinstance(image,Image):
            self.image = image
        else:
            print "Error, the image is actually not an image"

    def updateAxial(self,val):
        self.im_plot_axial.set_data(self.image.data[:,val,:])
        self.fig.canvas.draw()

    def onclickAxial(self,event):
        if event.inaxes is not None:
            ax = event.inaxes
            print ax
            print event.x, event.y
            self.im_plot_frontal.set_data(self.image.data[event.y,:,:])
            self.im_plot_sagittal.set_data(self.image.data[:,:,event.x])
            self.fig.canvas.draw()

    def show(self):
        import matplotlib.pyplot as plt
        self.fig = plt.figure()
        self.fig.subplots_adjust(bottom=0.1, left=0.1)

        self.im_size = self.image.data.shape

        ax = self.fig.add_subplot(221)
        self.im_plot_axial = ax.imshow(self.image.data[:,int(self.im_size[1]/2),:])
        self.im_plot_axial.set_cmap('gray')
        self.im_plot_axial.set_interpolation('nearest')

        ax = self.fig.add_subplot(222)
        self.im_plot_frontal = ax.imshow(self.image.data[int(self.im_size[0]/2),:,:])
        self.im_plot_frontal.set_cmap('gray')
        self.im_plot_frontal.set_interpolation('nearest')

        ax = self.fig.add_subplot(223)
        self.im_plot_sagittal = ax.imshow(self.image.data[:,:,int(self.im_size[2]/2)])
        self.im_plot_sagittal.set_cmap('gray')
        self.im_plot_sagittal.set_interpolation('nearest')

        trio = TrioPlot(self.im_plot_axial, self.im_plot_frontal, self.im_plot_sagittal, self.image)
        trio.connect()

        #slider_ax = self.fig.add_axes([0.15, 0.05, 0.75, 0.03])
        #slider_axial = Slider(slider_ax, 'Axial slices', 0, self.im_size[1], valinit=int(self.im_size[1]/2))
        #slider_axial.on_changed(self.updateAxial)

        plt.show()


#=======================================================================================================================
# Start program
#=======================================================================================================================
if __name__ == "__main__":
    parser = Parser(__file__)
    parser.usage.set_description('Volume Viewer')
    parser.add_option("-i", "file", "file", True)
    arguments = parser.parse(sys.argv[1:])

    image = Image(arguments["-i"])
    viewer = ClickViewer(image)
    viewer.start()
