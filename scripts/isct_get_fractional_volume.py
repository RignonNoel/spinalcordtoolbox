#!/usr/bin/env python
########################################################################################################################
#
# This script includes a function that enables to get the fractional volume of each labels from an atlas.
#
# ---------------------------------------------------------------------------------------
# Copyright (c) 2014 Polytechnique Montreal <www.neuro.polymtl.ca>
# Author(s): Simon LEVY
# Created: 2015-02-10
#
# About the license: see the file LICENSE.TXT
########################################################################################################################


def get_fractional_volume_per_label(atlas_folder, file_label, nb_RL_labels=15):
    """This function takes as input the path to the folder containing an atlas and the name of the file gathering the
    labels' file name of this atlas.
    It returns, in the following order:
    - a list of the labels' ID,
    - a list of the labels' name,
    - a 1D-numpy array containing the fractional volume of each label in the same order as the previous lists."""

    import sct_extract_metric
    import nibabel
    import numpy

    [label_id, label_name, label_file] = sct_extract_metric.read_label_file(atlas_folder, file_label)
    nb_label = len(label_file)

    fract_volume_per_lab = numpy.zeros((nb_label))

    # compute fractional volume for each label
    for i_label in range(0, nb_label):
        fract_volume_per_lab[i_label] = numpy.sum(nibabel.load(atlas_folder + label_file[i_label]).get_data())

    # gather right and left sides
    # nb_non_RL_labels = nb_label - (2*nb_RL_labels) # number of labels that are not paired side-wise
    fract_volume_per_lab_RL_gatehered = numpy.zeros((nb_RL_labels))
    label_name_RL_gatehered = []

    for i_label in range(0, nb_RL_labels):
        ind_ID_first_side = label_id.index(i_label)
        ind_ID_other_side = label_id.index(i_label + nb_RL_labels)

        fract_volume_per_lab_RL_gatehered[i_label] = fract_volume_per_lab[ind_ID_first_side] + fract_volume_per_lab[ind_ID_other_side]
        label_name_RL_gatehered.append(label_name[ind_ID_first_side].replace('left', '').replace('right', '').strip())

    # # add labels that are not paired side-wise
    # for i_label in range(0, nb_non_RL_labels):
    #     fract_volume_per_lab_RL_gatehered[nb_RL_labels+i_label] = fract_volume_per_lab[2 * nb_RL_labels + i_label]
    #     label_name_RL_gatehered.append(label_name[2 * nb_RL_labels + i_label].strip())

    return label_id, label_name, fract_volume_per_lab, label_name_RL_gatehered, fract_volume_per_lab_RL_gatehered