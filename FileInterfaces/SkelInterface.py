from ..FileReaders.SkelReader import SkelReader
from ..Utilities.Rotation import rotation_matrix_to_quat
import numpy as np


class SkelInterface:
    def __init__(self):
        self.rest_pose = []
        self.parent_bones = []
        self.unknown_data_1 = []
        self.bone_name_hashes = []
        self.unknown_data_3 = []
        self.uv_channel_material_name_hashes = []

        # Variables that will be removed eventually
        self.num_uv_channels = None

    @property
    def num_bones(self):
        return len(self.parent_bones)

    @classmethod
    def from_file(cls, path):
        with open(path, 'rb') as F:
            readwriter = SkelReader(F)
            readwriter.read()

        new_interface = cls()
        new_interface.num_uv_channels = readwriter.num_uv_channels

        new_interface.rest_pose = readwriter.bone_data
        new_interface.parent_bones = readwriter.parent_bones
        new_interface.unknown_data_1 = readwriter.unknown_data_1
        new_interface.bone_name_hashes = readwriter.bone_name_hashes
        new_interface.unknown_data_3 = readwriter.unknown_data_3
        new_interface.uv_channel_material_name_hashes = readwriter.uv_channel_material_name_hashes

        return new_interface

    def to_file(self, path):
        with open(path, 'wb') as F:
            readwriter = SkelReader(F)

            readwriter.filetype = '20SE'
            readwriter.num_bones = len(self.rest_pose)
            readwriter.num_uv_channels = self.num_uv_channels

            parent_bones = {c: p for c, p in self.parent_bones}
            bone_hierarchy = gen_bone_hierarchy(parent_bones)

            readwriter.num_bone_hierarchy_data_lines = len(bone_hierarchy)
            readwriter.bone_hierarchy_data = bone_hierarchy

            readwriter.bone_data = self.rest_pose
            readwriter.parent_bones = self.parent_bones
            readwriter.unknown_data_1 = self.unknown_data_1
            readwriter.bone_name_hashes = self.bone_name_hashes
            readwriter.unknown_data_3 = self.unknown_data_3
            readwriter.uv_channel_material_name_hashes = self.uv_channel_material_name_hashes

            # Just give up and make the absolute pointers
            readwriter.rel_ptr_to_end_of_bone_hierarchy_data = 40 + readwriter.num_bone_hierarchy_data_lines * 16
            readwriter.rel_ptr_to_end_of_bone_defs = readwriter.rel_ptr_to_end_of_bone_hierarchy_data + readwriter.num_bones * 12 * 4 - 4
            readwriter.rel_ptr_to_end_of_parent_bones = readwriter.rel_ptr_to_end_of_bone_defs + readwriter.num_bones * 2 - 16
            abs_end_of_parent_bones_chunk = readwriter.rel_ptr_to_end_of_parent_bones + readwriter.num_uv_channels + 44

            readwriter.rel_ptr_to_end_of_parent_bones_chunk = readwriter.rel_ptr_to_end_of_parent_bones + readwriter.num_uv_channels + 12
            readwriter.rel_ptr_to_end_of_parent_bones_chunk += (16 - ((abs_end_of_parent_bones_chunk) % 16)) % 16
            readwriter.rel_ptr_bone_name_hashes = readwriter.rel_ptr_to_end_of_parent_bones_chunk + readwriter.num_bones * 4 - 4
            readwriter.unknown_rel_ptr_3 = readwriter.rel_ptr_bone_name_hashes + readwriter.num_uv_channels * 4 - 4

            bytes_after_parent_bones_chunk = (readwriter.unknown_rel_ptr_3 + 40) - (
                        readwriter.rel_ptr_to_end_of_parent_bones_chunk + 32) + len(readwriter.uv_channel_material_name_hashes)
            bytes_after_parent_bones_chunk += (16 - (bytes_after_parent_bones_chunk % 16))

            readwriter.total_bytes = readwriter.rel_ptr_to_end_of_parent_bones_chunk + bytes_after_parent_bones_chunk + 32
            readwriter.remaining_bytes_after_parent_bones_chunk = bytes_after_parent_bones_chunk

            readwriter.padding_0x26 = 0
            readwriter.padding_0x2A = 0
            readwriter.padding_0x2E = 0
            readwriter.padding_0x32 = 0

            readwriter.write()

    def bone_data_from_armature_space(self, bone_matrices):
        bone_data = []
        parent_bones = {c: p for c, p in self.parent_bones}
        for i, bone_matrix in enumerate(bone_matrices):
            parent_idx = parent_bones[i]
            if parent_idx != -1:
                parent_bone_matrix = bone_matrices[parent_idx]

            else:
                parent_bone_matrix = np.eye(4)

            pr = parent_bone_matrix[:3, :3]
            cr = bone_matrix[:3, :3]
            rdiff = np.dot(pr.T, cr)
            rdiff = rotation_matrix_to_quat(rdiff)

            c_pos = bone_matrix[3, :3]
            p_pos = parent_bone_matrix[3, :3]
            diff = np.dot(pr.T, c_pos - p_pos)
            diff = (*diff, 1.)

            # Not really sure if setting the scale to always be 1 is legit, but...
            # eh, doesn't look like it's stored in the geom
            scal = (1., 1., 1., 1.)

            bd = [tuple(rdiff), diff, scal]
            bone_data.append(bd)
        return bone_data


def gen_bone_hierarchy(parent_bones):
    to_return = []
    parsed_bones = []
    bones_left_to_parse = [bidx for bidx in parent_bones]
    while len(bones_left_to_parse) > 0:
        hierarchy_line, new_parsed_bone_idxs = gen_bone_hierarchy_line(parent_bones, parsed_bones, bones_left_to_parse)
        to_return.append(hierarchy_line)

        for bidx in new_parsed_bone_idxs[::-1]:
            parsed_bones.append(bones_left_to_parse[bidx])
            del bones_left_to_parse[bidx]
    return to_return


def gen_bone_hierarchy_line(parent_bones, parsed_bones, bones_left_to_parse):
    """It ain't pretty, but it works"""
    to_return = []
    new_parsed_bone_idxs = []
    bone_iter = iter(bones_left_to_parse)
    prev_j = 0
    mod_j = -1
    for i in range(4):
        for j, bone in enumerate(bone_iter):
            mod_j = j + prev_j
            parent_bone = parent_bones[bone]
            if parent_bone == -1 or parent_bone in parsed_bones:
                to_return.append(bone)
                to_return.append(parent_bone)
                new_parsed_bone_idxs.append(mod_j)
                prev_j = mod_j + 1
                break
        if mod_j == len(bones_left_to_parse)-1 and len(to_return) < 8:
            to_return.extend(to_return[-2:])
    return to_return, new_parsed_bone_idxs
