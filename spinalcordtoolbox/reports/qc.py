#!/usr/bin/env python
# -*- coding: utf-8 -*-

import glob
import sys
import os
import fcntl
import json
import logging
import datetime
import io
from string import Template
from shutil import copyfile

import numpy as np
import skimage
import skimage.io
import skimage.exposure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.animation import FuncAnimation, PillowWriter
import matplotlib.colors as color

from spinalcordtoolbox.image import Image
import spinalcordtoolbox.reports.slice as qcslice
from spinalcordtoolbox.utils import sct_dir_local_path, list2cmdline, __version__, copy, extract_fname

logger = logging.getLogger(__name__)


class QcImage(object):
    """
    Class used to create a .png file from a 2d image produced by the class "Slice"
    """
    _labels_regions = {'PONS': 50, 'MO': 51,
                       'C1': 1, 'C2': 2, 'C3': 3, 'C4': 4, 'C5': 5, 'C6': 6, 'C7': 7,
                       'T1': 8, 'T2': 9, 'T3': 10, 'T4': 11, 'T5': 12, 'T6': 13, 'T7': 14, 'T8': 15, 'T9': 16,
                       'T10': 17, 'T11': 18, 'T12': 19,
                       'L1': 20, 'L2': 21, 'L3': 22, 'L4': 23, 'L5': 24,
                       'S1': 25, 'S2': 26, 'S3': 27, 'S4': 28, 'S5': 29,
                       'Co': 30}
    _color_bin_green = ["#ffffff", "#00ff00"]
    _color_bin_red = ["#ffffff", "#ff0000"]
    _labels_color = ["#04663c", "#ff0000", "#50ff30",
                     "#ed1339", "#ffffff", "#e002e8",
                     "#ffee00", "#00c7ff", "#199f26",
                     "#563691", "#848545", "#ce2fe1",
                     "#2142a6", "#3edd76", "#c4c253",
                     "#e8618a", "#3128a3", "#1a41db",
                     "#939e41", "#3bec02", "#1c2c79",
                     "#18584e", "#b49992", "#e9e73a",
                     "#3b0e6e", "#6e856f", "#637394",
                     "#36e05b", "#530a1f", "#8179c4",
                     "#e1320c", "#52a4df", "#000ab5",
                     "#4a4242", "#0b53a5", "#b49c19",
                     "#50e7a9", "#bf5a42", "#fa8d8e",
                     "#83839a", "#320fef", "#82ffbf",
                     "#360ee7", "#551960", "#11371e",
                     "#e900c3", "#a21360", "#58a601",
                     "#811c90", "#235acf", "#49395d",
                     "#9f89b0", "#e08e08", "#3d2b54",
                     "#7d0434", "#fb1849", "#14aab4",
                     "#a22abd", "#d58240", "#ac2aff"]
    _seg_colormap = ["#4d0000", "#ff0000"]
    _ctl_colormap = ["#ff000099", '#ffff00']

    def __init__(self, qc_report, interpolation, action_list, process, stretch_contrast=True,
                 stretch_contrast_method='contrast_stretching', angle_line=None, fps=None):
        """
        :param qc_report: QcReport: The QC report object
        :param interpolation: str: Type of interpolation used in matplotlib
        :param action_list: list: List of functions that generates a specific type of images
        :param process: str: Name of SCT function. e.g., sct_propseg
        :param stretch_contrast: adjust image so as to improve contrast
        :param stretch_contrast_method: str: {'contrast_stretching', 'equalized'}: Method for stretching contrast
        :param angle_line: float: See generate_qc()
        :param fps: float: Number of frames per second for output gif images. It is only used for sct_fmri_moco and\
        sct_dmri_moco
        """
        self.qc_report = qc_report
        self.interpolation = interpolation
        self.action_list = action_list
        self.process = process
        self._stretch_contrast = stretch_contrast
        self._stretch_contrast_method = stretch_contrast_method
        if stretch_contrast_method not in ['equalized', 'contrast_stretching']:
            raise ValueError("Unrecognized stretch_contrast_method: {}.".format(stretch_contrast_method),
                             "Try 'equalized' or 'contrast_stretching'")
        self._angle_line = angle_line
        self._fps = fps
        self._centermass = None  # center of mass returned by slice.Axial.get_center()
    """
    action_list contain the list of images that has to be generated.
    It can be seen as "figures" of matplotlib to be shown
    Ex: if 'colorbar' is in the list, the process will generate a color bar in the "img" folder
    """

    def line_angle(self, mask, ax):
        """Create figure with line superposed over each mosaic square. The line has an angle encoded in the
        argument self._angle_line"""
        angles = np.full_like(np.zeros(len(self._centermass)), np.nan)
        angles[0:len(self._angle_line)] = self._angle_line
        img = np.full_like(mask, np.nan)
        ax.imshow(img, cmap='gray', alpha=0, aspect=float(self.aspect_mask))
        for nslice, center_mosaic in enumerate(self._centermass):
            if np.isnan(angles[nslice]):
                pass
            else:
                x0, y0 = center_mosaic[0], center_mosaic[1]
                angle = angles[nslice]
                if not (-np.pi <= angle <= np.pi):
                    raise Exception("angle prompted for angle_line not in the range [-pi pi]")
                x_min, y_min = x0 - 10, y0 - 10
                x_max, y_max = x0 + 10, y0 + 10

                if -np.pi / 4 < angle <= np.pi / 4 or -np.pi <= angle <= -3 * np.pi / 4 or 3 * np.pi / 4 < angle <= np.pi:
                    y1 = y_min
                    y2 = y_max
                    x1 = (y_min - y0) * np.tan(angle) + x0
                    x2 = (y_max - y0) * np.tan(angle) + x0
                else:
                    x1 = x_min
                    x2 = x_max
                    y1 = y0 + (x_min - x0) / np.tan(angle)
                    y2 = y0 + (x_max - x0) / np.tan(angle)

                ax.plot([x1, x2], [y1, y2], '-', color='red', linewidth=0.7)

        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

    def listed_seg(self, mask, ax):
        """Create figure with red segmentation. Common scenario."""
        img = np.ma.masked_equal(mask, 0)
        ax.imshow(img,
                  cmap=color.LinearSegmentedColormap.from_list("", self._seg_colormap),
                  norm=color.Normalize(vmin=0.5, vmax=1),
                  interpolation=self.interpolation,
                  aspect=float(self.aspect_mask))
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

    def template(self, mask, ax):
        """Show template statistical atlas"""
        values = mask
        values[values < 0.5] = 0
        color_white = color.colorConverter.to_rgba('white', alpha=0.0)
        color_blue = color.colorConverter.to_rgba('blue', alpha=0.7)
        color_cyan = color.colorConverter.to_rgba('cyan', alpha=0.8)
        cmap = color.LinearSegmentedColormap.from_list('cmap_atlas',
                                                       [color_white, color_blue, color_cyan], N=256)
        ax.imshow(values,
                  cmap=cmap,
                  interpolation=self.interpolation,
                  aspect=self.aspect_mask)
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

    def no_seg_seg(self, mask, ax):
        """Create figure with image overlay. Notably used by sct_registration_to_template"""
        ax.imshow(mask, cmap='gray', interpolation=self.interpolation, aspect=self.aspect_mask)
        self._add_orientation_label(ax)
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

    def sequential_seg(self, mask, ax):
        values = np.ma.masked_equal(np.rint(mask), 0)
        ax.imshow(values,
                  cmap=self._seg_colormap,
                  interpolation=self.interpolation,
                  aspect=self.aspect_mask)
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

    def label_utils(self, mask, ax):
        """Create figure with red label. Common scenario."""
        img = np.full_like(mask, np.nan)
        ax.imshow(img, cmap='gray', alpha=0, aspect=float(self.aspect_mask))
        non_null_vox = np.where(mask > 0)
        coord_labels = list(zip(non_null_vox[0], non_null_vox[1]))
        logger.debug(coord_labels)
        # compute horizontal offset based on the resolution of the mask
        horiz_offset = mask.shape[1] / 50
        for coord in coord_labels:
            ax.plot(coord[1], coord[0], 'o', color='lime', markersize=5)
            ax.text(coord[1] + horiz_offset, coord[0], str(round(mask[coord[0], coord[1]])), color='lime', fontsize=15,
                    verticalalignment='center', clip_on=True)
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

    def label_vertebrae(self, mask, ax):
        """Draw vertebrae areas, then add text showing the vertebrae names"""
        from matplotlib import colors
        import scipy.ndimage
        img = np.rint(np.ma.masked_where(mask < 1, mask))
        labels = np.unique(img[np.where(~img.mask)]).astype(int)  # get available labels
        ax.imshow(img,
                  cmap=colors.ListedColormap(self._labels_color[labels.min():labels.max()+1]),  # get color from min label and max label
                  interpolation=self.interpolation,
                  alpha=1,
                  aspect=float(self.aspect_mask))
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)
        a = [0.0]
        data = mask
        for index, val in np.ndenumerate(data):
            if val not in a:
                a.append(val)
                index = int(val)
                if index in self._labels_regions.values():
                    color = self._labels_color[index]
                    y, x = scipy.ndimage.measurements.center_of_mass(np.where(data == val, data, 0))
                    # Draw text with a shadow
                    x += 10
                    label = list(self._labels_regions.keys())[list(self._labels_regions.values()).index(index)]
                    ax.text(x, y, label, color='black', clip_on=True)
                    x -= 0.5
                    y -= 0.5
                    ax.text(x, y, label, color=color, clip_on=True)

    def highlight_pmj(self, mask, ax):
        """Hook to show a rectangle where PMJ is on the slice"""
        y, x = np.where(mask == 50)
        img = np.full_like(mask, np.nan)
        ax.imshow(img, cmap='gray', alpha=0, aspect=float(self.aspect_mask))
        ax.plot(x, y, 'x', color='lime', markersize=6)
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

    def label_centerline(self, mask, ax):
        """Create figure with red label. Common scenario."""
        results_mask_pixels = np.where(mask > 0)
        # TODO: maybe we only need one pixel per centerline (currently, it's a 1x2 matrix of pixels)
        listOfCoordinates = list(zip(results_mask_pixels[0], results_mask_pixels[1]))
        for cord in listOfCoordinates:
            ax.plot(cord[1], cord[0], 'ro', markersize=1)
            # ax.text(cord[1]+5,cord[0]+5, str(mask[cord]), color='lime', clip_on=True)
        img = np.rint(np.ma.masked_where(mask < 1, mask))
        ax.imshow(img,
                  cmap=color.ListedColormap(self._color_bin_red),
                  norm=color.Normalize(vmin=0, vmax=1),
                  interpolation=self.interpolation,
                  alpha=10,
                  aspect=float(self.aspect_mask))
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

    def vertical_line(self, mask, ax):
        """Centered vertical line to assess quality of straightening"""
        img = np.full_like(mask, np.nan)
        ax.imshow(img, cmap='gray', alpha=0, aspect=float(self.aspect_mask))
        ax.axvline(x=img.shape[1] / 2.0, color='r', linewidth=2)
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

    def grid(self, mask, ax):
        """Centered grid to assess quality of motion correction"""
        grid = np.full_like(mask, 0)
        ax.imshow(grid, cmap='gray', alpha=0, aspect=float(self.aspect_mask))
        for center_mosaic in self._centermass:
            x0, y0 = center_mosaic[0], center_mosaic[1]
            ax.axvline(x=x0, color='w', linestyle='-', linewidth=0.5)
            ax.axhline(y=y0, color='w', linestyle='-', linewidth=0.5)
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

    def smooth_centerline(self, mask, ax):
        """Display smoothed centerline"""
        mask = mask/mask.max()
        mask[mask < 0.05] = 0  # Apply 0.5 threshold
        img = np.ma.masked_equal(mask, 0)
        ax.imshow(img,
                  cmap=color.LinearSegmentedColormap.from_list("", self._ctl_colormap),
                  norm=color.Normalize(vmin=0, vmax=1),
                  interpolation=self.interpolation,
                  aspect=float(self.aspect_mask))
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

    # def colorbar(self):
    #     fig = plt.figure(figsize=(9, 1.5))
    #     ax = fig.add_axes([0.05, 0.80, 0.9, 0.15])
    #     colorbar.ColorbarBase(ax, cmap=self._seg_colormap, orientation='horizontal')
    #     return '{}_colorbar'.format(self.qc_report.img_base_name)

    def __call__(self, func):
        """wrapped function (f).

        In this case, it is the "mosaic" or "single" methods of the class "Slice"
        """

        def wrapped_f(sct_slice, *args):
            """

            :param sct_slice: spinalcordtoolbox.report.slice:Slice
            :param args: list: list of args
            """
            self.qc_report.slice_name = sct_slice.get_name()

            # Get the aspect ratio (height/width) based on pixel size. Consider only the first 2 slices.
            self.aspect_img, self.aspect_mask = sct_slice.aspect()[:2]

            self.qc_report.make_content_path()
            logger.info('QcImage: %s with %s slice', func.__name__, sct_slice.get_name())

            if self.process in ['sct_fmri_moco', 'sct_dmri_moco']:
                [images_after_moco, images_before_moco], centermass = func(sct_slice, *args)
                self._centermass = centermass
                self._make_QC_image_for_4d_volumes(images_after_moco, images_before_moco)
            else:
                if self._angle_line is None:
                    img, *mask = func(sct_slice, *args)
                else:
                    [img, mask], centermass = func(sct_slice, *args)
                    self._centermass = centermass

                self._make_QC_image_for_3d_volumes(img, mask, slice_orientation=sct_slice.get_name())

        return wrapped_f

    def _make_QC_image_for_3d_volumes(self, img, mask, slice_orientation):
        """
        Create overlay and background images for all processes that deal with 3d volumes
        (all except sct_fmri_moco and sct_dmri_moco)

        :param img: The base image to display underneath the overlays (typically anatomical)
        :param mask: A list of images to be processed and overlaid on top of `img`
        :return:
        """

        if self._stretch_contrast:
            img = self._func_stretch_contrast(img)

        # if axial mosaic restrict width
        if slice_orientation == 'Axial':
            size_fig = [5, 5 * img.shape[0] / img.shape[1]]  # with dpi=300, will give 1500pix width
        # if sagittal orientation restrict height
        elif slice_orientation == 'Sagittal':
            size_fig = [5 * img.shape[1] / img.shape[0], 5]

        fig = Figure()
        fig.set_size_inches(size_fig[0], size_fig[1], forward=True)
        FigureCanvas(fig)
        ax = fig.add_axes((0, 0, 1, 1))
        ax.imshow(img, cmap='gray', interpolation=self.interpolation, aspect=float(self.aspect_img))
        self._add_orientation_label(ax)
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)
        logger.info(self.qc_report.qc_params.abs_bkg_img_path())
        self._save(fig, self.qc_report.qc_params.abs_bkg_img_path(), dpi=self.qc_report.qc_params.dpi)

        fig = Figure()
        fig.set_size_inches(size_fig[0], size_fig[1], forward=True)
        FigureCanvas(fig)
        for i, action in enumerate(self.action_list):
            logger.debug('Action List %s', action.__name__)
            if self._stretch_contrast and action.__name__ in ("no_seg_seg",):
                print("Mask type %s" % mask[i].dtype)
                mask[i] = self._func_stretch_contrast(mask[i])
            ax = fig.add_axes((0, 0, 1, 1), label=str(i))
            action(self, mask[i], ax)
        self._save(fig, self.qc_report.qc_params.abs_overlay_img_path(), dpi=self.qc_report.qc_params.dpi)

        self.qc_report.update_description_file(img.shape)

    def _make_QC_image_for_4d_volumes(self, images_after_moco, images_before_moco):
        """
        Generate background and overlay gifs for sct_fmri_moco and sct_dmri_moco

        :param images_after_moco: list of mosaic images after motion correction
        :param images_before_moco: list of mosaic images before motion correction
        :return:
        """

        size_fig = [5, 10 * images_after_moco[0].shape[0] / images_after_moco[0].shape[1] + 0.5]
        if self._stretch_contrast:
            for i in range(len(images_after_moco)):
                images_after_moco[i] = self._func_stretch_contrast(images_after_moco[i])
                images_before_moco[i] = self._func_stretch_contrast(images_before_moco[i])

        self._generate_and_save_gif(images_before_moco, images_after_moco, size_fig)
        self._generate_and_save_gif(images_before_moco, images_after_moco, size_fig, is_mask=True)

        w, h = (self.qc_report.qc_params.dpi * size_fig[0], self.qc_report.qc_params.dpi * size_fig[1])
        self.qc_report.update_description_file((w, h))

    def _func_stretch_contrast(self, img):
        if self._stretch_contrast_method == "equalized":
            return self._equalize_histogram(img)
        else:  # stretch_contrast_method == "contrast_stretching":
            return self._stretch_intensity_levels(img)

    def _stretch_intensity_levels(self, img):
        p2, p98 = np.percentile(img, (2, 98))
        return skimage.exposure.rescale_intensity(img, in_range=(p2, p98))

    def _equalize_histogram(self, img):
        """
        Perform histogram equalization using CLAHE

        Notes:

        - Image value range is preserved
        - Workaround for adapthist artifact by padding (#1664)
        """
        winsize = 16
        min_, max_ = img.min(), img.max()
        b = (np.float32(img) - min_) / (max_ - min_)
        b[b >= 1] = 1  # 1+eps numerical error may happen (#1691)

        h, w = b.shape
        h1 = (h + (winsize - 1)) // winsize * winsize
        w1 = (w + (winsize - 1)) // winsize * winsize
        if h != h1 or w != w1:
            b1 = np.zeros((h1, w1), dtype=b.dtype)
            b1[:h, :w] = b
            b = b1
        c = skimage.exposure.equalize_adapthist(b, kernel_size=(winsize, winsize))
        if h != h1 or w != w1:
            c = c[:h, :w]

        return np.array(c * (max_ - min_) + min_, dtype=img.dtype)

    def _add_orientation_label(self, ax):
        """
        Add orientation labels on the figure

        :param fig: MPL figure handler
        :return:
        """
        if self.qc_report.qc_params.orientation == 'Axial':
            # If mosaic of axial slices, display orientation labels
            ax.text(12, 6, 'A', color='yellow', size=4)
            ax.text(12, 28, 'P', color='yellow', size=4)
            ax.text(0, 18, 'L', color='yellow', size=4)
            ax.text(24, 18, 'R', color='yellow', size=4)

    def _generate_and_save_gif(self, top_images, bottom_images, size_fig, is_mask=False):
        """
        Create figure with two images for sct_fmri_moco and sct_dmri_moco and save gif

        :param top_images: list of images of mosaic before motion correction
        :param bottom_images: list of images of mosaic after motion correction
        :param size_fig: size of figure in inches
        :param is_mask: display grid on top of mosaic
        :return:
        """

        if is_mask:
            aspect = self.aspect_mask
        else:
            aspect = self.aspect_img

        fig = Figure()
        FigureCanvas(fig)
        fig.set_size_inches(size_fig[0], size_fig[1], forward=True)
        fig.subplots_adjust(left=0, top=0.9, bottom=0.1)

        ax1 = fig.add_subplot(211)
        null_image = np.zeros(np.shape(top_images[0]))
        img1 = ax1.imshow(null_image, cmap='gray', aspect=float(aspect))
        ax1.set_title('Before motion correction', fontsize=8, loc='left', pad=2)
        ax1.get_xaxis().set_visible(False)
        ax1.get_yaxis().set_visible(False)
        self._add_orientation_label(ax1)
        if is_mask:
            QcImage.grid(self, top_images[0], ax1)

        ax2 = fig.add_subplot(212)
        img2 = ax2.imshow(null_image, cmap='gray', aspect=float(aspect))
        ax2.set_title('After motion correction', fontsize=8, loc='left', pad=2)
        ax2.get_xaxis().set_visible(False)
        ax2.get_yaxis().set_visible(False)
        self._add_orientation_label(ax2)
        if is_mask:
            QcImage.grid(self, bottom_images[0], ax2)

        ann = ax2.annotate('', xy=(0, .025), xycoords='figure fraction', horizontalalignment='left',
                           verticalalignment='bottom', fontsize=6)

        def update_figure(i):
            img1.set_data(top_images[i])
            img1.set_clim(vmin=np.amin(top_images[i]), vmax=np.amax(top_images[i]))
            img2.set_data(bottom_images[i])
            img2.set_clim(vmin=np.amin(bottom_images[i]), vmax=np.amax(bottom_images[i]))
            ann.set_text(f'Volume: {i + 1}/{len(top_images)}')

        # FuncAnimation creates an animation by repeatedly calling the function update_figure for each frame
        ani = FuncAnimation(fig, update_figure, frames=len(top_images))

        if is_mask:
            gif_out_path = self.qc_report.qc_params.abs_overlay_img_path()
        else:
            gif_out_path = self.qc_report.qc_params.abs_bkg_img_path()

        if self._fps is None:
            self._fps = 3
        writer = PillowWriter(self._fps)
        logger.info('Saving gif %s', gif_out_path)
        ani.save(gif_out_path, writer=writer, dpi=self.qc_report.qc_params.dpi)

    def _save(self, fig, img_path, format='png', bbox_inches='tight', pad_inches=0.00, dpi=300):
        """
        Save the current figure into an image.

        :param fig: Figure handler
        :param img_path: str: path of the folder where the image is saved
        :param format: str: image format
        :param bbox_inches: str
        :param pad_inches: float
        :param dpi: int: Output resolution of the image
        :return:
        """
        logger.debug('Save image %s', img_path)
        fig.savefig(img_path,
                    format=format,
                    bbox_inches=None,
                    transparent=True,
                    dpi=dpi)


class Params(object):
    """Parses and stores the variables that will be included into the QC details
    """

    def __init__(self, input_file, command, args, orientation, dest_folder, dpi=300, dataset=None, subject=None):
        """

        :param input_file: str: the input nifti file name
        :param command: str: command name
        :param args: str: the command's arguments
        :param orientation: str: The anatomical orientation
        :param dest_folder: str: The absolute path of the QC root
        :param dpi: int: Output resolution of the image
        :param dataset: str: Dataset name
        :param subject: str: Subject name
        """
        path_in, file_in, ext_in = extract_fname(os.path.abspath(input_file))
        # Assuming BIDS convention, we derive the value of the dataset, subject and contrast from the `input_file`
        # by splitting it into `[dataset]/[subject]/[contrast]/input_file`
        abs_input_path, contrast = os.path.split(path_in)
        abs_input_path, subject_tmp = os.path.split(abs_input_path)
        _, dataset_tmp = os.path.split(abs_input_path)
        if dataset is None:
            dataset = dataset_tmp
        if subject is None:
            subject = subject_tmp
        if isinstance(args, list):
            args = list2cmdline(args)
        self.fname_in = file_in + ext_in
        self.dataset = dataset
        self.subject = subject
        self.cwd = os.getcwd()
        self.contrast = contrast
        self.command = command
        self.sct_version = __version__
        self.args = args
        self.orientation = orientation
        self.dpi = dpi
        self.root_folder = dest_folder
        self.mod_date = datetime.datetime.strftime(datetime.datetime.now(), '%Y_%m_%d_%H%M%S.%f')
        self.qc_results = os.path.join(dest_folder, '_json/qc_' + self.mod_date + '.json')
        if command in ['sct_fmri_moco', 'sct_dmri_moco']:
            ext = "gif"
        else:
            ext = "png"
        self.bkg_img_path = os.path.join(dataset, subject, contrast, command, self.mod_date, f"bkg_img.{ext}")
        self.overlay_img_path = os.path.join(dataset, subject, contrast, command, self.mod_date, f"overlay_img.{ext}")

    def abs_bkg_img_path(self):
        return os.path.join(self.root_folder, self.bkg_img_path)

    def abs_overlay_img_path(self):
        return os.path.join(self.root_folder, self.overlay_img_path)


class QcReport(object):
    """This class generates the quality control report.

    It will also setup the folder structure so the report generator only needs to fetch the appropriate files.
    """

    def __init__(self, qc_params, usage):
        """
        Parameters

        :param qc_params: arguments of the "-param-qc" option in Terminal
        :param usage: str: description of the process
        """
        self.tool_name = qc_params.command
        self.slice_name = qc_params.orientation
        self.qc_params = qc_params
        self.usage = usage
        self.assets_folder = sct_dir_local_path('assets')
        self.img_base_name = 'bkg_img'
        self.description_base_name = "qc_results"

    def make_content_path(self):
        """Creates the whole directory to contain the QC report

        :return: return "root folder of the report" and the "furthest folder path" containing the images
        """
        # make a new or update Qc directory
        target_img_folder = os.path.dirname(self.qc_params.abs_bkg_img_path())
        try:
            os.makedirs(target_img_folder, exist_ok=True)
        except OSError as err:
            if not os.path.isdir(target_img_folder):
                raise err

    def update_description_file(self, dimension):
        """Create the description file with a JSON structure

        :param: dimension 2-tuple, the dimension of the image frame (w, h)
        """

        output = {
            'python': sys.executable,
            'cwd': self.qc_params.cwd,
            'cmdline': "{} {}".format(self.qc_params.command, self.qc_params.args),
            'command': self.qc_params.command,
            'sct_version': self.qc_params.sct_version,
            'dataset': self.qc_params.dataset,
            'subject': self.qc_params.subject,
            'contrast': self.qc_params.contrast,
            'fname_in': self.qc_params.fname_in,
            'orientation': self.qc_params.orientation,
            'background_img': self.qc_params.bkg_img_path,
            'overlay_img': self.qc_params.overlay_img_path,
            'dimension': '%dx%d' % dimension,
            'moddate': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'qc': ""
        }
        logger.debug('Description file: %s', self.qc_params.qc_results)
        # results = []
        # Create path to store json files
        path_json, _ = os.path.split(self.qc_params.qc_results)
        if not os.path.exists(path_json):
            os.makedirs(path_json, exist_ok=True)

        # lock the output directory
        # because this code may be run in parallel
        path_json_fd = os.open(path_json, os.O_RDONLY)
        fcntl.flock(path_json_fd, fcntl.LOCK_EX)

        try:
            # Create json file
            with open(self.qc_params.qc_results, 'w+') as qc_file:
                json.dump(output, qc_file, indent=1)
            self._update_html_assets(get_json_data_from_path(path_json))
        finally:
            # fcntl.flock(path_json_fd, fcntl.LOCK_UN) # technically, redundant, since close() triggers this too.
            os.close(path_json_fd)

    def _update_html_assets(self, json_data):
        """Update the html file and assets"""
        assets_path = os.path.join(os.path.dirname(__file__), 'assets')
        dest_path = self.qc_params.root_folder

        with io.open(os.path.join(assets_path, 'index.html'), encoding="utf-8") as template_index:
            template = Template(template_index.read())
            output = template.substitute(sct_json_data=json.dumps(json_data))
            io.open(os.path.join(dest_path, 'index.html'), 'w', encoding="utf-8").write(output)

        for path in ['css', 'js', 'imgs', 'fonts']:
            src_path = os.path.join(assets_path, '_assets', path)
            dest_full_path = os.path.join(dest_path, '_assets', path)
            if not os.path.exists(dest_full_path):
                os.makedirs(dest_full_path, exist_ok=True)
            for file_ in os.listdir(src_path):
                if not os.path.isfile(os.path.join(dest_full_path, file_)):
                    copy(os.path.join(src_path, file_),
                             dest_full_path)


def add_entry(src, process, args, path_qc, plane, path_img=None, path_img_overlay=None,
              qcslice=None,
              qcslice_operations=[],
              qcslice_layout=None,
              dpi=300,
              stretch_contrast_method='contrast_stretching',
              angle_line=None,
              fps=None,
              dataset=None,
              subject=None):
    """
    Create QC report.

    :param src: Path to input file (only used to populate report metadata)
    :param process:
    :param args:
    :param path_qc:
    :param plane:
    :param path_img: Path to image to display
    :param path_img_overlay: Path to image to display on top of path_img (will flip between the two)
    :param qcslice: spinalcordtoolbox.reports.slice:Axial or spinalcordtoolbox.reports.slice:Sagittal
    :param qcslice_operations:
    :param qcslice_layout:
    :param dpi: int: Output resolution of the image
    :param stretch_contrast_method: Method for stretching contrast. See QcImage
    :param angle_line: [float]: See generate_qc()
    :param fps: float: Number of frames per second for output gif images
    :param dataset: str: Dataset name
    :param subject: str: Subject name
    :return:
    """

    qc_param = Params(src, process, args, plane, path_qc, dpi, dataset, subject)
    report = QcReport(qc_param, '')

    if qcslice is not None:
        @QcImage(report, 'none', qcslice_operations, stretch_contrast_method=stretch_contrast_method,
                 angle_line=angle_line, process=process, fps=fps)
        def layout(qslice):
            # This will call qc.__call__(self, func):
            return qcslice_layout(qslice)

        layout(qcslice)
    elif path_img is not None:
        report.make_content_path()
        report.update_description_file(skimage.io.imread(path_img).shape[:2])
        copyfile(path_img, qc_param.abs_bkg_img_path())
        if path_img_overlay is not None:
            # User specified a second image to overlay
            copyfile(path_img_overlay, qc_param.abs_overlay_img_path())
        else:
            # Copy the image both as "overlay" and "path_img_overlay", so it appears static.
            # TODO: Leave the possibility in the reports/assets/js files to have static images (instead of having to
            #  flip between two images).
            copyfile(path_img, qc_param.abs_overlay_img_path())

    logger.info('Successfully generated the QC results in %s', qc_param.qc_results)
    logger.info('Use the following command to see the results in a browser:')
    try:
        from sys import platform as _platform
        if _platform == "linux" or _platform == "linux2":
            # If user runs SCT within the official Docker distribution, the command xdg-open will not be working therefore
            # we prefer to instruct the user to manually open the generated html file.
            try:
                # if user runs SCT within the official Docker distribution, the variable below is defined. More info at:
                # https://github.com/neuropoly/sct_docker/blob/master/sct_docker.py#L84
                os.environ["DOCKER"]
                logger.info('please go to "%s/" and double click on the "index.html" file', path_qc)
            except KeyError:
                logger.info('xdg-open "%s/index.html"', path_qc)

        elif _platform == "darwin":
            logger.info('open "%s/index.html"', path_qc)
        else:
            logger.info('open file "%s/index.html"', path_qc)
    except ImportError:
        print("WARNING! Platform undetectable.")


def generate_qc(fname_in1, fname_in2=None, fname_seg=None, angle_line=None, args=None, path_qc=None,
                dataset=None, subject=None, path_img=None, process=None, fps=None):
    """
    Generate a QC entry allowing to quickly review results. This function is the entry point and is called by SCT
    scripts (e.g. sct_propseg).

    :param fname_in1: str: File name of input image #1 (mandatory)
    :param fname_in2: str: File name of input image #2
    :param fname_seg: str: File name of input segmentation
    :param angle_line: list: Angle [in rad, wrt. vertical line, must be between -pi and pi] to apply to the line overlaid on the image, for\
    each slice, for slice that don't have an angle to display, a nan is expected. To be used for assessing cord orientation.
    :param args: args from parent function
    :param path_qc: str: Path to save QC report
    :param dataset: str: Dataset name
    :param subject: str: Subject name
    :param path_img: dict: Path to image to display (e.g., a graph), instead of computing the image from MRI.
    :param process: str: Name of SCT function. e.g., sct_propseg
    :param fps: float: Number of frames per second for output gif images. Used only for sct_frmi_moco and sct_dmri_moco.
    :return: None
    """
    logger.info('\n*** Generate Quality Control (QC) html report ***')
    dpi = 300
    plane = None
    qcslice_type = None
    qcslice_operations = None
    qcslice_layout = None

    # Get QC specifics based on SCT process
    # Axial orientation, switch between two input images
    if process in ['sct_register_multimodal', 'sct_register_to_template']:
        plane = 'Axial'
        qcslice_type = qcslice.Axial([Image(fname_in1), Image(fname_in2), Image(fname_seg)])
        qcslice_operations = [QcImage.no_seg_seg]
        def qcslice_layout(x): return x.mosaic()[:2]
    # Rotation visualisation
    elif process in ['rotation']:
        plane = 'Axial'
        qcslice_type = qcslice.Axial([Image(fname_in1), Image(fname_seg)])
        qcslice_operations = [QcImage.line_angle]
        def qcslice_layout(x): return x.mosaic(return_center=True)
    # Axial orientation, switch between the image and the segmentation
    elif process in ['sct_propseg', 'sct_deepseg_sc', 'sct_deepseg_gm']:
        plane = 'Axial'
        qcslice_type = qcslice.Axial([Image(fname_in1), Image(fname_seg)])
        qcslice_operations = [QcImage.listed_seg]
        def qcslice_layout(x): return x.mosaic()
    # Axial orientation, switch between the image and the centerline
    elif process in ['sct_get_centerline']:
        plane = 'Axial'
        qcslice_type = qcslice.Axial([Image(fname_in1), Image(fname_seg)])
        qcslice_operations = [QcImage.label_centerline]
        def qcslice_layout(x): return x.mosaic()
    # Axial orientation, switch between the image and the white matter segmentation (linear interp, in blue)
    elif process in ['sct_warp_template']:
        plane = 'Axial'
        qcslice_type = qcslice.Axial([Image(fname_in1), Image(fname_seg)])
        qcslice_operations = [QcImage.template]
        def qcslice_layout(x): return x.mosaic()
    # Axial orientation, switch between gif image (before and after motion correction) and grid overlay
    elif process in ['sct_dmri_moco', 'sct_fmri_moco']:
        plane = 'Axial'
        if fname_seg is None:
            raise Exception("Segmentation is needed to ensure proper cropping around spinal cord.")
        qcslice_type = qcslice.Axial([Image(fname_in1), Image(fname_in2), Image(fname_seg)])
        qcslice_operations = [QcImage.grid]
        def qcslice_layout(x): return x.mosaics_through_time()
    # Sagittal orientation, display vertebral labels
    elif process in ['sct_label_vertebrae']:
        plane = 'Sagittal'
        dpi = 100  # bigger picture is needed for this special case, hence reduce dpi
        qcslice_type = qcslice.Sagittal([Image(fname_in1), Image(fname_seg)], p_resample=None)
        qcslice_operations = [QcImage.label_vertebrae]
        def qcslice_layout(x): return x.single()
    #  Sagittal orientation, display posterior labels
    elif process in ['sct_label_utils']:
        plane = 'Sagittal'
        dpi = 100  # bigger picture is needed for this special case, hence reduce dpi
        # projected_image = projected(Image(fname_seg))
        qcslice_type = qcslice.Sagittal([Image(fname_in1), Image(fname_seg)], p_resample=None)
        qcslice_operations = [QcImage.label_utils]
        def qcslice_layout(x): return x.single()
    # Sagittal orientation, display PMJ box
    elif process in ['sct_detect_pmj']:
        plane = 'Sagittal'
        qcslice_type = qcslice.Sagittal([Image(fname_in1), Image(fname_seg)], p_resample=None)
        qcslice_operations = [QcImage.highlight_pmj]
        def qcslice_layout(x): return x.single()
    # Sagittal orientation, static image
    elif process in ['sct_straighten_spinalcord']:
        plane = 'Sagittal'
        dpi = 100
        qcslice_type = qcslice.Sagittal([Image(fname_in1), Image(fname_in1)], p_resample=None)
        qcslice_operations = [QcImage.vertical_line]
        def qcslice_layout(x): return x.single()
    # Metric outputs (only graphs)
    elif process in ['sct_process_segmentation']:
        plane = 'Sagittal'
        dpi = 100  # bigger picture is needed for this special case, hence reduce dpi
        fname_list = [fname_in1]
        # fname_seg should be a list of 4 images: 3 for each of the `qcslice_operations`, plus an extra
        # centerline image, which is needed to make `Sagittal.get_center_spit` work correctly
        fname_list.extend(fname_seg)
        qcslice_type = qcslice.Sagittal([Image(fname) for fname in fname_list], p_resample=None)
        qcslice_operations = [QcImage.smooth_centerline, QcImage.highlight_pmj, QcImage.listed_seg]
        def qcslice_layout(x): return x.single()
    else:
        raise ValueError("Unrecognized process: {}".format(process))

    add_entry(
        src=fname_in1,
        process=process,
        args=args,
        path_qc=path_qc,
        dataset=dataset,
        subject=subject,
        plane=plane,
        path_img=path_img,
        dpi=dpi,
        qcslice=qcslice_type,
        qcslice_operations=qcslice_operations,
        qcslice_layout=qcslice_layout,
        stretch_contrast_method='equalized',
        angle_line=angle_line,
        fps=fps
    )


def get_json_data_from_path(path_json):
    """Read all json files present in the given path, and output an aggregated json structure"""
    results = []
    for file_json in glob.iglob(os.path.join(path_json, '*.json')):
        logger.debug('Opening: ' + file_json)
        with open(file_json, 'r+') as fjson:
            results.append(json.load(fjson))
    return results
