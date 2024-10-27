import os

import dearpygui.dearpygui as dpg
import open3d as o3d
from time import time, sleep
import numpy as np
import json
import binvox_file
import trimesh

dpg.create_context()

# Функции, описывающие решетчатую структуру
# Гироид
func_gyroid = lambda x_coord, y_coord, z_coord, l: (np.sin(x_coord / l) * np.cos(y_coord / l) +
                                                    np.sin(y_coord / l) * np.cos(z_coord / l) +
                                                    np.sin(z_coord / l) * np.cos(x_coord / l))
# Поверхность Шварца P
func_primitive = lambda x_coord, y_coord, z_coord, l: np.cos(x_coord / l) + np.cos(y_coord / l) + np.cos(z_coord / l)

# Поверхность Шварца D
func_diamond = lambda x_coord, y_coord, z_coord, l: (np.sin(x_coord / l) * np.sin(y_coord / l) * np.sin(z_coord / l) +
                                                     np.sin(x_coord / l) * np.cos(y_coord / l) * np.cos(z_coord / l) +
                                                     np.cos(x_coord / l) * np.sin(y_coord / l) * np.cos(z_coord / l) +
                                                     np.cos(x_coord / l) * np.cos(y_coord / l) * np.sin(z_coord / l))


class Create_Connection:
    instances = []

    def __init__(self, sender, app_data):
        self.sender = sender
        self.links = None
        self.target = app_data
        self.from_child = None
        self.to_child = None
        self.status = True

    def redo(self):
        self.links = dpg.add_node_link(self.target[0], self.target[1], parent=self.sender)
        # print(self.links, self.target)
        self.from_child = dpg.get_item_children(item=self.target[0], slot=1)[0]
        self.to_child = dpg.get_item_children(item=self.target[1], slot=1)[0]
        dpg.set_value(item=self.to_child, value=dpg.get_value(self.from_child))
        Create_Connection.instances.append(self)
        # print(Create_Connection.instances)

    def undo(self):
        dpg.delete_item(self.links)

    @classmethod
    def get_connection_by_attr(cls, target):
        return [inst for inst in cls.instances if inst.target[0] == target]

    @classmethod
    def get_connection_by_tag(cls, tag):
        return [inst for inst in cls.instances if inst.links == tag]


class Delete_Connection:
    def __init__(self, sender, app_data):
        self.sender = sender
        self.links = app_data
        self.target = None
        self.selected_links = dpg.get_selected_links(node_editor=self.sender)

    def redo(self):
        # print(self.selected_links)
        if not self.selected_links:
            for item in history.actions:
                if item.__class__ == Create_Connection:
                    if item.links == self.links:
                        item.status = False
                        dpg.hide_item(self.links)
                        # dpg.configure_item(item=self.links, enabled=False)
        else:
            for link in self.selected_links:
                # print(self.selected_links)
                for item in history.actions:
                    if item.__class__ == Create_Connection:
                        if item.links == link:
                            item.status = False
                            dpg.hide_item(link)

    def undo(self):
        if not self.selected_links:
            dpg.configure_item(item=self.links, show=True)
            for item in history.actions:
                if item.__class__ == Create_Connection:
                    if item.links == self.links:
                        item.status = True
        else:
            for link in self.selected_links:
                for item in history.actions:
                    if item.__class__ == Create_Connection:
                        if item.links == link:
                            item.status = True
                            dpg.configure_item(item=link, show=True)


class History:
    actions = []  # [action object]
    nodes = []  # [node object]
    index = 0
    n_index = 0
    out = {'nodes': [], 'links': []}

    def undo(self):
        if self.index > 0:
            self.actions[self.index - 1].undo()
            self.index -= 1

    def redo(self):
        if self.index < len(self.actions):
            if self.index > 30:
                self.actions.pop(0)
            self.actions[self.index].redo()
            self.index += 1

    def add(self, a):

        if self.index >= 30:
            self.actions.pop(0)
            self.index -= 1
        self.actions.append(a)
        self.index += 1
        if a.__class__ == Create_Node:
            self.nodes.append(a.node_object)

    def to_json(self):
        out_1 = {'nodes': [], 'links': []}
        for i in range(len(self.actions)):
            item = {}

            if self.actions[i].__class__ == Create_Node:
                if self.actions[i].node_object.status:
                    item['fields'] = self.actions[i].node_object.__dict__
                    try:
                        item['fields']['value'] = dpg.get_value(self.actions[i].node_object.out)
                    except AttributeError:
                        item['fields']['value'] = dpg.get_value(self.actions[i].node_object.inp_1)
                    item['position'] = dpg.get_item_pos(self.actions[i].node_id)
                    self.out['nodes'].append(item)
                    out_1['nodes'].append(item)
            elif self.actions[i].__class__ == Create_Connection and self.actions[i].status:
                item['fields'] = self.actions[i].__dict__
                self.out['links'].append(item)
                out_1['links'].append(item)
        out_2 = json.dumps(out_1, indent=4)
        with open('data.json', "w") as f:
            f.truncate()
            f.write(out_2)

    def from_json(self, file):
        with open(file, 'r') as f:
            data = json.load(f)
        for i in data.keys():
            self.out[i] = data[i]
        self.recover_project_from_json()

    def recover_project_from_json(self):
        link_targets = []

        for link in self.out['links']:
            link_fields = link['fields']
            link_targets += link_fields['target']
        new_targets = [0] * len(link_targets)

        for item in self.out['nodes']:
            item_fields = item['fields']
            node_id = item_fields['node_id']
            label = item_fields['label']
            position = item['position']
            value = item_fields['value']

            node = Create_Node(label, node_id)
            node.node_object.value = value
            history.add(node)

            dpg.set_item_pos(item=node.node_id, pos=position)
            children = dpg.get_item_children(item=node.node_id, slot=1)

            if len(children) == 1:
                grandchild = dpg.get_item_children(item=children[0], slot=1)[0]
                dpg.set_value(item=grandchild, value=value)
            else:
                grandchild = dpg.get_item_children(item=children[-1], slot=1)[-2]
                dpg.set_value(item=grandchild, value=value)

            key_list = list(item_fields.keys())
            val_list = list(item_fields.values())

            for i in range(len(link_targets)):
                try:

                    attr_position = val_list.index(link_targets[i])
                    new_targets[i] = node.node_object.__dict__[key_list[attr_position]]
                except ValueError:
                    pass
        for i in range(0, len(new_targets) - 1, 2):
            try:
                con = Create_Connection(sender='node_editor', app_data=[new_targets[i], new_targets[i + 1]])
                con.redo()
            except Exception:
                pass
            history.add(con)


class Move_Node:
    def __init__(self, dx=50, dy=50):
        self.selected_nodes = dpg.get_selected_nodes(node_editor='node_editor')
        self.dx = dx
        self.dy = dy
        self.current_position = [15, 15]
        self.redo()

    def redo(self):
        for node in self.selected_nodes:
            current_position = dpg.get_item_pos(node)
            current_position[0] += self.dx
            current_position[1] += self.dy
            self.current_position = current_position
            dpg.set_item_pos(item=node, pos=current_position)

    def undo(self):
        for node in self.selected_nodes:
            current_position = dpg.get_item_pos(node)
            current_position[0] -= self.dx
            current_position[1] -= self.dy
            dpg.set_item_pos(item=node, pos=current_position)


class Drop_Node:
    def __init__(self, node_id):
        self.node_id = node_id
        self.current_position = None
        self.previous_position = None
        self.redo()

    def redo(self):
        for item in history.nodes:
            if item.node_id == self.node_id:
                if self.current_position == dpg.get_item_pos(self.node_id):
                    self.current_position = self.previous_position
                    self.previous_position = dpg.get_item_pos(self.node_id)
                else:
                    self.current_position = dpg.get_item_pos(self.node_id)
                    self.previous_position = item.position
                    item.position = self.current_position
                    dpg.set_item_pos(item=self.node_id, pos=self.current_position)

    def undo(self):
        for item in history.nodes:
            if item.node_id == self.node_id:
                pos = dpg.get_item_pos(self.node_id)
                self.current_position = self.previous_position
                self.previous_position = pos
                item.position = self.current_position
                dpg.set_item_pos(item=self.node_id, pos=self.current_position)


class Create_Node:
    def __init__(self, label, node_id=None):
        self.id = dpg.generate_uuid()
        self.label = label
        if node_id is None:
            self.node_id = self.id
        else:
            self.node_id = f'node_{node_id}'
        self.node_object = None
        self.redo()

    def redo(self):
        if self.label == 'Cell Thickness':
            self.node_object = Node_Cell_Thickness(node_id=self.node_id, label=self.label)
        elif self.label == 'STL File':
            self.node_object = Node_STL_File(node_id=self.node_id, label=self.label)
        elif self.label == 'View STL':
            self.node_object = Node_View_STL(node_id=self.node_id, label=self.label)
        elif self.label == 'Cuda Voxelizer':
            self.node_object = Node_Cuda_Voxelizer(node_id=self.node_id, label=self.label)
        elif self.label == 'Trimesh Voxelizer':
            self.node_object = Node_Trimesh_Voxelizer(node_id=self.node_id, label=self.label)
        elif self.label == 'Voxel Grid':
            self.node_object = Node_Voxel_Grid(node_id=self.node_id, label=self.label)
        elif self.label == 'Cell Length':
            self.node_object = Node_Cell_Length(node_id=self.node_id, label=self.label)
        elif self.label == 'Lattice Pattern':
            self.node_object = Node_Lattice_Pattern(node_id=self.node_id, label=self.label)
        elif self.label == 'Lattice':
            self.node_object = Node_Lattice(node_id=self.node_id, label=self.label)

    def undo(self):
        try:
            dpg.hide_item(item=self.node_id)
            self.node_object.status = False
        except SystemError:
            pass


class Delete_Node:
    def __init__(self):
        self.selected_nodes = dpg.get_selected_nodes(node_editor='node_editor')
        self.redo()

    def redo(self):
        for node in self.selected_nodes:
            for item in history.nodes:
                if item.node_id == node:
                    item.status = False
                    dpg.hide_item(node)

    def undo(self):
        for node in self.selected_nodes:
            for item in history.nodes:
                if item.node_id == node:
                    item.status = True
                    dpg.configure_item(item=node, pos=dpg.get_item_pos(node), show=True)


class Node_Cell_Thickness:
    def __init__(self, node_id, label):
        self.node_id = node_id
        self.position = [15, 15]
        self.label = label
        self.attr_1 = None
        self.out = None
        self.value = 0.2
        self.status = True
        self.create_node()

    def create_node(self):
        node = dpg.add_node(label=self.label,
                            tag=self.node_id,
                            pos=self.position,
                            parent='node_editor',
                            draggable=True,
                            drag_callback=drag_n_drop,
                            )

        self.attr_1 = dpg.add_node_attribute(attribute_type=dpg.mvNode_Attr_Output,
                                             parent=node)
        self.out = dpg.add_input_float(default_value=self.value,
                                       tag=dpg.generate_uuid(),
                                       max_value=1,
                                       min_value=0,
                                       min_clamped=True,
                                       max_clamped=True,
                                       width=100,
                                       callback=self.update,
                                       parent=self.attr_1)

    def update(self, *args):
        current_value = dpg.get_value(item=self.out)
        if current_value != self.value:
            self.value = current_value
            connections = Create_Connection.get_connection_by_attr(self.attr_1)
            for con in connections:
                dpg.set_value(item=con.to_child, value=self.value)


class Node_STL_File:
    def __init__(self, node_id, label):
        self.node_id = node_id
        self.position = [15, 15]
        self.label = label
        self.attr_1 = None
        self.out = None
        self.value = 'No file selected'
        self.status = True
        self.create_node()

    def create_node(self):

        node = dpg.add_node(label=self.label,
                            tag=self.node_id,
                            pos=self.position,
                            parent='node_editor',
                            draggable=True,
                            )

        self.attr_1 = dpg.add_node_attribute(label='STL File -> STL File',
                                             attribute_type=dpg.mvNode_Attr_Output,
                                             parent=node)

        self.out = dpg.add_input_text(default_value=self.value,
                                      width=200,
                                      parent=self.attr_1,
                                      tag=dpg.generate_uuid(),
                                      )
        button = dpg.add_button(label='Choose file', tag=dpg.generate_uuid(), parent=self.attr_1,
                                width=200, callback=self.create_file_dialog, user_data=self.out)

    def create_file_dialog(self, sender, app_data, user_data):
        file_dialog = dpg.add_file_dialog(label='STL File Search', tag=dpg.generate_uuid(),
                                          width=500, height=300, callback=self.set_value, user_data=user_data)
        extension = dpg.add_file_extension(label='STL File Extension', extension='.stl',
                                           tag=dpg.generate_uuid(), parent=file_dialog)

    def set_value(self, sender, app_data, user_data):
        dpg.set_value(item=user_data, value=app_data['file_path_name'])
        self.update()

    def update(self):
        current_value = dpg.get_value(item=self.out)
        if current_value != self.value:
            self.value = current_value
            connections = Create_Connection.get_connection_by_attr(self.attr_1)
            for con in connections:
                if dpg.get_item_configuration(con.links)["show"]:
                    dpg.set_value(item=con.to_child, value=self.value)


class Node_View_STL:
    def __init__(self, node_id, label):
        self.node_id = node_id
        self.position = [15, 15]
        self.label = label
        self.attr_1 = None
        self.inp_1 = None
        self.value = 'STL File Path'
        self.status = True
        self.create_node()

    def create_node(self):
        node = dpg.add_node(label=self.label,
                            tag=self.node_id,
                            pos=self.position,
                            parent='node_editor',
                            draggable=True,
                            )
        self.attr_1 = dpg.add_node_attribute(attribute_type=dpg.mvNode_Attr_Input,
                                             parent=node,
                                             tag=dpg.generate_uuid())
        self.inp_1 = dpg.add_input_text(default_value=self.value, tag=dpg.generate_uuid(),
                                        parent=self.attr_1, width=200)
        button = dpg.add_button(label='View', tag=dpg.generate_uuid(), parent=self.attr_1,
                                width=200, callback=self.view, user_data=self.inp_1)

    def view(self, sender, app_data, user_data):
        file_path = dpg.get_value(item=user_data)
        mesh = o3d.io.read_triangle_mesh(file_path)
        mesh = mesh.compute_vertex_normals()
        o3d.visualization.draw_geometries([mesh], window_name="STL", left=1000, top=200, width=800, height=650)


class Node_Trimesh_Voxelizer:
    def __init__(self, node_id, label):
        self.node_id = node_id
        self.label = label
        self.position = [15, 15]
        self.attr_1 = None
        self.attr_2 = None
        self.attr_3 = None
        self.inp_1 = None
        self.inp_2 = None
        self.out = None
        self.value = None
        self.status = True
        self.create_node()

    def create_node(self):
        node = dpg.add_node(label=self.label,
                            tag=self.node_id,
                            pos=self.position,
                            parent='node_editor',
                            draggable=True,
                            )
        self.attr_1 = dpg.add_node_attribute(label='Trimesh Voxelizer -> STL File',
                                             attribute_type=dpg.mvNode_Attr_Input,
                                             parent=node,
                                             tag=dpg.generate_uuid())
        self.attr_2 = dpg.add_node_attribute(label='Trimesh Voxelizer -> Pitch',
                                             attribute_type=dpg.mvNode_Attr_Static,
                                             parent=node,
                                             tag=dpg.generate_uuid())
        self.attr_3 = dpg.add_node_attribute(label='Voxel Grid instance',
                                             attribute_type=dpg.mvNode_Attr_Output,
                                             parent=node,
                                             tag=dpg.generate_uuid())
        self.inp_1 = dpg.add_input_text(default_value='STL File',
                                        tag=dpg.generate_uuid(),
                                        parent=self.attr_1,
                                        width=250,
                                        readonly=True)
        self.inp_2 = dpg.add_input_float(default_value=0.01,
                                         tag=dpg.generate_uuid(),
                                         parent=self.attr_2,
                                         width=250,
                                         readonly=False)
        self.out = dpg.add_text(default_value='', tag=dpg.generate_uuid(),
                                parent=self.attr_3, show=False)
        button = dpg.add_button(label='Voxelize', tag=dpg.generate_uuid(), parent=self.attr_3,
                                width=200, callback=self.voxelize)

    def voxelize(self):
        file_path = dpg.get_value(self.inp_1)
        pitch = dpg.get_value(self.inp_2)
        mesh = trimesh.exchange.load.load_mesh(file_obj=file_path, file_type='stl')
        voxel_array = trimesh.voxel.creation.voxelize(mesh=mesh, pitch=pitch,
                                                      )
        voxel = trimesh.voxel.morphology.fill(encoding=voxel_array.matrix, method='orthographic')
        # print(voxel.dense)
        val = json.dumps(voxel.dense.tolist())
        with open('data1.json', "w") as f:
            f.truncate()
            f.write(val)
        self.value = 'data1.json'
        dpg.set_value(item=self.out, value=self.value)


class Node_Cuda_Voxelizer:
    def __init__(self, node_id, label):
        self.node_id = node_id
        self.label = label
        self.position = [15, 15]
        self.attr_1 = None
        self.attr_2 = None
        self.attr_3 = None
        self.inp_1 = None
        self.inp_2 = None
        self.out = None
        self.value = None
        self.status = True
        self.create_node()

    def create_node(self):
        node = dpg.add_node(label=self.label,
                            tag=self.node_id,
                            pos=self.position,
                            parent='node_editor',
                            draggable=True,
                            )
        self.attr_1 = dpg.add_node_attribute(label='Cuda Voxelizer -> STL File',
                                             attribute_type=dpg.mvNode_Attr_Input,
                                             parent=node,
                                             tag=dpg.generate_uuid())
        self.attr_2 = dpg.add_node_attribute(label='Cuda Voxelizer -> Voxel Grid',
                                             attribute_type=dpg.mvNode_Attr_Input,
                                             parent=node,
                                             tag=dpg.generate_uuid())
        self.attr_3 = dpg.add_node_attribute(label='Binvox File Path',
                                             attribute_type=dpg.mvNode_Attr_Output,
                                             parent=node,
                                             tag=dpg.generate_uuid())
        self.inp_1 = dpg.add_input_text(default_value='STL File',
                                        tag=dpg.generate_uuid(),
                                        parent=self.attr_1,
                                        width=250,
                                        readonly=True)
        self.inp_2 = dpg.add_input_int(default_value=0,
                                       tag=dpg.generate_uuid(),
                                       parent=self.attr_2,
                                       width=250,
                                       readonly=True)
        self.out = dpg.add_text(default_value='Binvox File Path', tag=dpg.generate_uuid(),
                                parent=self.attr_3, show=False)
        button = dpg.add_button(label='Voxelize', tag=dpg.generate_uuid(), parent=self.attr_3,
                                width=200, callback=self.voxelize, user_data=[self.inp_1, self.inp_2, self.out])

    def voxelize(self, *args):
        file_path = dpg.get_value(item=self.inp_1)
        voxel_grid = dpg.get_value(item=self.inp_2)
        out = self.out
        command = f'cuda_voxelizer -f {file_path} -s {voxel_grid} -o binvox -solid'
        os.system(command)
        dpg.set_value(item=out, value=f'{file_path}_{voxel_grid}.binvox')
        self.update()

    def update(self):
        current_value = dpg.get_value(item=self.out)
        if current_value != self.value:
            self.value = current_value
            connections = Create_Connection.get_connection_by_attr(self.attr_3)
            for con in connections:
                dpg.set_value(item=con.to_child, value=self.value)


class Node_Voxel_Grid:
    def __init__(self, node_id, label):
        self.node_id = node_id
        self.label = label
        self.position = [15, 15]
        self.attr_1 = None
        self.out = None
        self.value = 256
        self.status = True
        self.create_node()

    def create_node(self):
        node = dpg.add_node(label=self.label,
                            tag=self.node_id,
                            pos=self.position,
                            parent='node_editor',
                            draggable=True,
                            )
        self.attr_1 = dpg.add_node_attribute(label='Voxel Grid -> Voxel Grid',
                                             attribute_type=dpg.mvNode_Attr_Output,
                                             parent=node)
        self.out = dpg.add_input_int(default_value=self.value,
                                     min_value=0,
                                     max_value=4096,
                                     min_clamped=True,
                                     max_clamped=True,
                                     width=100,
                                     step=10,
                                     step_fast=100,
                                     parent=self.attr_1,
                                     callback=self.update,
                                     tag=dpg.generate_uuid(),
                                     )

    def update(self, *args):
        current_value = dpg.get_value(item=self.out)
        if current_value != self.value:
            self.value = current_value
            connections = Create_Connection.get_connection_by_attr(self.attr_1)
            for con in connections:
                dpg.set_value(item=con.to_child, value=self.value)


class Node_Cell_Length:
    def __init__(self, node_id, label):
        self.node_id = node_id
        self.label = label
        self.position = [15, 15]
        self.attr_1 = None
        self.out = None
        self.value = 5
        self.status = True
        self.create_node()

    def create_node(self):
        # print(sender)
        node = dpg.add_node(label=self.label,
                            tag=self.node_id,
                            pos=self.position,
                            parent='node_editor',
                            draggable=True,
                            )
        self.attr_1 = dpg.add_node_attribute(label='Cell Length -> Length',
                                             attribute_type=dpg.mvNode_Attr_Output,
                                             parent=node,
                                             tag=dpg.generate_uuid())
        self.out = dpg.add_input_int(default_value=5,
                                     min_value=0,
                                     max_value=50,
                                     min_clamped=True,
                                     max_clamped=True,
                                     width=100,
                                     step=1,
                                     step_fast=10,
                                     parent=self.attr_1,
                                     callback=self.update,
                                     tag=dpg.generate_uuid(),
                                     )

    def update(self, *args):
        current_value = dpg.get_value(item=self.out)
        if current_value != self.value:
            self.value = current_value
            connections = Create_Connection.get_connection_by_attr(self.attr_1)
            for con in connections:
                dpg.set_value(item=con.to_child, value=self.value)


class Node_Lattice_Pattern:
    def __init__(self, node_id, label):
        self.node_id = node_id
        self.label = label
        self.position = [15, 15]
        self.attr_1 = None
        self.out = None
        self.value = 'Choose a pattern'
        self.status = True
        self.create_node()

    def create_node(self):
        node = dpg.add_node(label=self.label,
                            tag=self.node_id,
                            pos=self.position,
                            parent='node_editor',
                            draggable=True,
                            )
        self.attr_1 = dpg.add_node_attribute(label='Lattice Pattern -> Pattern',
                                             attribute_type=dpg.mvNode_Attr_Output,
                                             parent=node,
                                             tag=dpg.generate_uuid())

        self.out = dpg.add_combo(items=['Gyroid', 'Diamond', 'Primitive'],
                                 default_value=self.value,
                                 width=200,
                                 parent=self.attr_1,
                                 callback=self.update,
                                 tag=dpg.generate_uuid())

    def update(self, *args):
        current_value = dpg.get_value(item=self.out)
        if current_value != self.value:
            self.value = current_value
            connections = Create_Connection.get_connection_by_attr(self.attr_1)
            for con in connections:
                dpg.set_value(item=con.to_child, value=self.value)


class Node_Lattice:
    def __init__(self, node_id, label):
        self.node_id = node_id
        self.label = label
        self.position = [15, 15]
        self.pattern_func = None
        self.cell_thickness = None
        self.cell_length = None
        self.voxel_array = []
        self.dims = []
        self.output_file = None
        self.attr_1 = None
        self.attr_2 = None
        self.attr_3 = None
        self.attr_4 = None
        self.attr_5 = None
        self.inp_1 = None
        self.inp_2 = None
        self.inp_3 = None
        self.inp_4 = None
        self.out = None
        self.value = 'STL File Path'
        self.status = True
        self.create_node()

    def create_node(self):
        node = dpg.add_node(label=self.label,
                            tag=self.node_id,
                            pos=self.position,
                            parent='node_editor',
                            draggable=True
                            )
        self.attr_1 = dpg.add_node_attribute(label='Lattice -> Voxel Model',
                                             attribute_type=dpg.mvNode_Attr_Input,
                                             parent=node,
                                             tag=dpg.generate_uuid())
        self.attr_2 = dpg.add_node_attribute(label='Lattice -> Cell Length',
                                             attribute_type=dpg.mvNode_Attr_Input,
                                             parent=node,
                                             tag=dpg.generate_uuid())
        self.attr_3 = dpg.add_node_attribute(label='Lattice -> Cell Thickness',
                                             attribute_type=dpg.mvNode_Attr_Input,
                                             parent=node,
                                             tag=dpg.generate_uuid())
        self.attr_4 = dpg.add_node_attribute(label='Lattice -> Pattern',
                                             attribute_type=dpg.mvNode_Attr_Input,
                                             parent=node,
                                             tag=dpg.generate_uuid())

        self.attr_5 = dpg.add_node_attribute(label='Lattice -> STL File',
                                             attribute_type=dpg.mvNode_Attr_Output,
                                             parent=node,
                                             tag=dpg.generate_uuid())
        self.inp_1 = dpg.add_input_text(default_value='Voxel Model',
                                        tag=dpg.generate_uuid(),
                                        parent=self.attr_1,
                                        width=250,
                                        readonly=True)
        self.inp_2 = dpg.add_input_int(default_value=0,
                                       tag=dpg.generate_uuid(),
                                       parent=self.attr_2,
                                       width=250,
                                       readonly=True)
        helping_text_1 = dpg.add_text(default_value='Cell Length', parent=self.attr_2)
        self.inp_3 = dpg.add_input_float(default_value=0,
                                         tag=dpg.generate_uuid(),
                                         parent=self.attr_3,
                                         width=250,
                                         readonly=True)
        helping_text_2 = dpg.add_text(default_value='Cell Thickness', parent=self.attr_3)

        self.inp_4 = dpg.add_input_text(default_value='Lattice Pattern',
                                        tag=dpg.generate_uuid(),
                                        parent=self.attr_4,
                                        width=250,
                                        readonly=True)
        self.out = dpg.add_text(default_value=self.value, tag=dpg.generate_uuid(), parent=self.attr_5, show=False)

        button = dpg.add_button(label='Generate Lattice', tag=dpg.generate_uuid(), parent=self.attr_5,
                                width=250, callback=self.lattice)

    def lattice(self, *args):
        file_path = dpg.get_value(item=self.inp_1)

        self.cell_length = dpg.get_value(item=self.inp_2)
        self.cell_thickness = dpg.get_value(self.inp_3)
        pattern = dpg.get_value(item=self.inp_4)

        self.set_pattern(pattern)

        if file_path.split('.')[-1] == 'json':
            self.voxel_model_trimesh(file_path)
        elif file_path.split('.')[-1] == 'binvox':
            self.read_binvox(file_path)

        self.make_structure()

        self.write_to_stl(file_path)
        dpg.set_value(item=self.out, value=f'{file_path}.stl')
        self.update()

    def set_pattern(self, pattern):
        if pattern == 'Gyroid':
            self.pattern_func = func_gyroid
        elif pattern == 'Diamond':
            self.pattern_func = func_diamond
        else:
            self.pattern_func = func_primitive

    def read_binvox(self, file_path):
        with open(file_path, 'rb') as f:
            model = binvox_file.read_as_3d_array(f)
        # Сохранение всех параметров модели
        self.voxel_array = model.data
        self.dims = model.dims

    def voxel_model_trimesh(self, file_path):
        with open(file_path, "r") as f:
            self.voxel_array = np.array(json.load(f), dtype=float)
        self.dims = np.shape(self.voxel_array)

    def make_structure(self):
        for x in range(self.dims[0]):
            for y in range(self.dims[1]):
                for z in range(self.dims[2]):
                    if self.voxel_array[x][y][z]:
                        self.voxel_array[x][y][z] = 0 \
                            if abs(self.pattern_func(x, y, z, self.cell_length)) > self.cell_thickness else 1

    def write_to_stl(self, path):
        print(self.voxel_array)
        # Используется метод matrix_to_marching_cubes из бибилиотеки trimesh
        mesh = trimesh.voxel.ops.matrix_to_marching_cubes(
            matrix=self.voxel_array,
            pitch=.20)
        print("Merging vertices closer than a pre-set constant...")
        mesh.merge_vertices()
        print("Removing duplicate faces...")
        mesh.update_faces(mesh.unique_faces())
        # mesh.remove_duplicate_faces()
        print("Scaling...")
        mesh.apply_scale(scaling=1.0)
        print("Making the mesh watertight...")
        trimesh.repair.fill_holes(mesh)
        print("Fixing inversion and winding...")
        trimesh.repair.fix_inversion(mesh)
        trimesh.repair.fix_winding(mesh)

        # Сохранение STL-файла
        print("Generating the STL mesh file")
        trimesh.exchange.export.export_mesh(
            mesh=mesh,
            file_obj=f'{path}.stl',

            file_type="stl"
        )

    def update(self):
        current_value = dpg.get_value(item=self.out)
        if current_value != self.value:
            self.value = current_value
            connections = Create_Connection.get_connection_by_attr(self.attr_5)
            for con in connections:
                dpg.set_value(item=con.to_child, value=self.value)


"""
class Node_Subtraction(Node_Base):
    def __init__(self, node_id, label):
        self.node_id = node_id
        self.label = label
        self.position = [15, 15]
        self.attr_1 = None
        self.inp_1 = None
        self.attr_2 = None
        self.inp_2 = None
        self.attr_3 = None
        self.out = None
        self.value = 'Voxel Model'
        self.status = True
        self.create_node()

    def create_node(self):
        node = dpg.add_node(label=self.label,
                            tag=self.node_id,
                            pos=self.position,
                            parent='node_editor',
                            draggable=True,
                            )
        self.attr_1 = dpg.add_node_attribute(label='Voxel Model 1',
                                             attribute_type=dpg.mvNode_Attr_Input,
                                             parent=node,
                                             tag=dpg.generate_uuid())

        self.inp_1 = dpg.add_input_text(default_value=self.value,
                                        width=250,
                                        parent=self.attr_1,
                                        # callback=self.update,
                                        tag=dpg.generate_uuid(),
                                        readonly=True)
        self.attr_2 = dpg.add_node_attribute(label='Voxel Model 2',
                                             attribute_type=dpg.mvNode_Attr_Input,
                                             parent=node,
                                             tag=dpg.generate_uuid())

        self.inp_2 = dpg.add_input_text(default_value=self.value,
                                        width=250,
                                        parent=self.attr_2,
                                        # callback=self.update,
                                        tag=dpg.generate_uuid(),
                                        readonly=True)
        self.attr_3 = dpg.add_node_attribute(label='Voxel Model 2',
                                             attribute_type=dpg.mvNode_Attr_Output,
                                             parent=node,
                                             tag=dpg.generate_uuid())

        self.out = dpg.add_text(default_value='Voxel Model', parent=self.attr_3,
                                tag=dpg.generate_uuid(), show=True)
        button = dpg.add_button(label='Subtract', tag=dpg.generate_uuid(), parent=self.attr_3,
                                width=200, callback=self.subtraction, user_data=[self.inp_1, self.inp_2, self.out])

    def subtraction(self):
        pass

"""


class Main_Window:
    def __init__(self):
        dpg.add_window(label="Tutorial", width=800, height=800, tag='main_window', no_close=False, no_move=False)
        dpg.bind_item_theme(item='main_window', theme=Main_Window.createTheme())

        dpg.add_template_registry(tag='template_registry')
        dpg.add_node_editor(callback=link, delink_callback=delink,
                            tag='node_editor', parent='main_window',
                            minimap=True, minimap_location=1)
        # dpg.add_value_registry(tag='value_registry')

        self.global_handler()
        dpg.add_item_handler_registry(tag='movement_handler')
        dpg.add_item_handler_registry(tag='del_handler')
        dpg.add_menu_bar(tag='main_menu_bar', parent='main_window')
        dpg.add_menu(label="Input Nodes", parent='main_menu_bar', tag='menu_input_nodes')

        dpg.add_menu_item(label='STL File', tag='STL File Menu', user_data='STL File',
                          parent='menu_input_nodes', callback=create_node)
        dpg.add_tooltip(tag='STL File tooltip', parent='STL File Menu')
        dpg.add_text(default_value='Node to choose STL File from directory', parent='STL File tooltip')

        dpg.add_menu_item(label='Voxel Grid', tag='Voxel Grid Menu', user_data='Voxel Grid',
                          parent='menu_input_nodes', callback=create_node)
        dpg.add_tooltip(tag='Voxel Grid tooltip', parent='Voxel Grid Menu')
        dpg.add_text(default_value='Node to set voxel grid for voxelization', parent='Voxel Grid tooltip')

        dpg.add_menu_item(label='Cell Length', tag='Cell Length Menu', user_data='Cell Length',
                          parent='menu_input_nodes', callback=create_node)
        dpg.add_tooltip(tag='Cell Length tooltip', parent='Cell Length Menu')
        dpg.add_text(default_value='Node to set cell length to generate lattice structure',
                     parent='Cell Length tooltip')

        dpg.add_menu_item(label='Cell Thickness', tag='Cell Thickness Menu', user_data='Cell Thickness',
                          parent='menu_input_nodes', callback=create_node)
        dpg.add_tooltip(tag='Cell Thickness tooltip', parent='Cell Thickness Menu')
        dpg.add_text(default_value='Node to set cell thickness to generate lattice structure',
                     parent='Cell Thickness tooltip')

        dpg.add_menu_item(label='Lattice Pattern', tag='Lattice Pattern Menu', user_data='Lattice Pattern',
                          parent='menu_input_nodes', callback=create_node)
        dpg.add_tooltip(tag='Lattice Pattern tooltip', parent='Lattice Pattern Menu')
        dpg.add_text(default_value='Node to set lattice pattern to generate lattice structure',
                     parent='Lattice Pattern tooltip')

        dpg.add_menu(label="Functional Nodes", parent='main_menu_bar', tag='menu_functional_nodes')

        dpg.add_menu_item(label='Cuda Voxelizer', tag='Cuda Voxelizer Menu', user_data='Cuda Voxelizer',
                          parent='menu_functional_nodes', callback=create_node)
        dpg.add_tooltip(tag='Cuda Voxelizer tooltip', parent='Cuda Voxelizer Menu')
        with dpg.group(parent='Cuda Voxelizer tooltip'):
            dpg.add_text(default_value='Node for voxelization using Cuda Voxelizer')
            dpg.add_text(default_value='Required params:')
            dpg.add_text(default_value='STL File', bullet=True)
            dpg.add_text(default_value='Voxel Grid', bullet=True)

        dpg.add_menu_item(label='Trimesh Voxelizer', tag='Trimesh Voxelizer Menu', user_data='Trimesh Voxelizer',
                          parent='menu_functional_nodes', callback=create_node)
        dpg.add_tooltip(tag='Trimesh Voxelizer tooltip', parent='Trimesh Voxelizer Menu')
        with dpg.group(parent='Trimesh Voxelizer tooltip'):
            dpg.add_text(default_value='Node for voxelization using Trimesh Voxelizer')
            dpg.add_text(default_value='Required params:')
            dpg.add_text(default_value='STL File', bullet=True)
            dpg.add_text(default_value='Pitch - size of a voxel side', bullet=True)

        dpg.add_menu_item(label='Lattice', tag='Lattice Menu', user_data='Lattice',
                          parent='menu_functional_nodes', callback=create_node)
        dpg.add_tooltip(tag='Lattice tooltip', parent='Lattice Menu')
        with dpg.group(parent='Lattice tooltip'):
            dpg.add_text(default_value='Node to generate lattice structure')
            dpg.add_text(default_value='Required params:')
            dpg.add_text(default_value='Binvox File', bullet=True)
            dpg.add_text(default_value='Cell Length', bullet=True)
            dpg.add_text(default_value='Cell Thickness', bullet=True)
            dpg.add_text(default_value='Lattice Pattern', bullet=True)

        dpg.add_menu(label="View Nodes", parent='main_menu_bar', tag='menu_view_nodes')
        dpg.add_menu_item(label='View STL', tag='View STL Menu', user_data='View STL',
                          parent='menu_view_nodes', callback=create_node)
        dpg.add_tooltip(tag='View STL tooltip', parent='View STL Menu')
        dpg.add_text(default_value='Node to visualize STL File', parent='View STL tooltip')

        dpg.add_button(label='Save', tag='save_button', parent='main_menu_bar', indent=990, callback=save,
                       width=100, height=35)

        self.import_file_path = dpg.add_text(default_value='No path', parent='main_menu_bar', show=False)
        dpg.add_button(label='Import Project', tag=dpg.generate_uuid(),
                       parent='main_menu_bar', indent=1100, width=150, height=35, track_offset=0.1,
                       callback=Main_Window.import_project_file_dialog, user_data=self.import_file_path)

    @staticmethod
    def import_project_file_dialog(sender, app_data, user_data):
        file_dialog = dpg.add_file_dialog(label='JSON File Search', tag=dpg.generate_uuid(),
                                          width=500, height=300, user_data=user_data,
                                          callback=Main_Window.set_value)
        extension = dpg.add_file_extension(label='JSON File Extension', extension='.json',
                                           tag=dpg.generate_uuid(), parent=file_dialog)

    @staticmethod
    def set_value(sender, app_data, user_data):
        dpg.set_value(item=user_data, value=app_data['file_path_name'])
        history.from_json(file=app_data['file_path_name'])

    def global_handler(self):
        dpg.add_handler_registry(tag='global_handler')
        kph = dpg.add_key_press_handler(callback=key, parent='global_handler')
        mph = dpg.add_mouse_release_handler(button=dpg.mvMouseButton_Left, parent='global_handler',
                                            callback=drag_n_drop)

    @staticmethod
    def createTheme():
        with dpg.theme() as themeTag:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=5, y=5, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowBorderSize, x=0, y=0, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=12, y=16, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameBorderSize, x=0, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_ItemSpacing, x=8, y=9, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_ItemInnerSpacing, x=5, y=9, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_CellPadding, x=5, y=9, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_PopupBorderSize, x=2, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_PopupRounding, x=3, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_ScrollbarRounding, x=10, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_GrabMinSize, x=16, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_GrabRounding, x=5, category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_FrameBgHovered, value=(40, 40, 40),
                                    category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_FrameBgActive, value=(30, 30, 30),
                                    category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_ButtonHovered, value=(40, 40, 40),
                                    category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_ButtonActive, value=(30, 30, 30),
                                    category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_WindowBg, value=(30, 30, 30),
                                    category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_MenuBarBg, value=(33, 38, 99),
                                    category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_Border, value=(0, 0, 0), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_BorderShadow, value=(0, 0, 0),
                                    category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_SliderGrab, value=(25, 107, 52),
                                    category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_SliderGrabActive, value=(44, 150, 79),
                                    category=dpg.mvThemeCat_Core)

                dpg.add_theme_style(target=dpg.mvNodeStyleVar_NodeCornerRounding, x=9,
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_style(target=dpg.mvNodeStyleVar_NodePadding, x=11, y=10,
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_style(target=dpg.mvNodeStyleVar_NodeBorderThickness, x=2,
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_style(target=dpg.mvNodeStyleVar_PinQuadSideLength, x=8, category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_style(target=dpg.mvNodeStyleVar_PinTriangleSideLength, x=8,
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_style(target=dpg.mvNodeStyleVar_PinCircleRadius, x=4, category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_style(target=dpg.mvNodeStyleVar_PinOffset, x=-1, category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_style(target=dpg.mvNodeStyleVar_LinkThickness, x=2, category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_style(target=dpg.mvNodeStyleVar_LinkLineSegmentsPerLength, x=2,
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_style(target=dpg.mvNodesStyleVar_MiniMapPadding, x=1, y=1,
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_style(target=dpg.mvNodeStyleVar_GridSpacing, x=40, y=40,
                                    category=dpg.mvThemeCat_Nodes)
                # dpg.add_theme_color(target=dpg.mvThemeCol_Button, value=(0, 0, 0),
                # category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvNodeCol_NodeOutline, value=(0, 0, 0),
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_color(target=dpg.mvNodeCol_TitleBar, value=(33, 38, 99),  # (80, 40, 60),
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_color(target=dpg.mvNodeCol_TitleBarHovered, value=(105, 137, 204),  # (100, 60, 80),
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_color(target=dpg.mvNodeCol_TitleBarSelected, value=(75, 105, 166),
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_color(target=dpg.mvNodeCol_NodeBackground, value=(82, 82, 82),
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_color(target=dpg.mvNodeCol_Pin, value=(252, 197, 119),
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_color(target=dpg.mvNodeCol_PinHovered, value=(252, 186, 93),
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_color(target=dpg.mvNodeCol_Link, value=(252, 197, 119),
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_color(target=dpg.mvNodeCol_GridLine, value=(30, 30, 30, 255),
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_color(target=dpg.mvNodeCol_GridBackground, value=(50, 50, 50, 255),
                                    category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_color(target=dpg.mvNodesCol_MiniMapOutline, value=(0, 0, 0),
                                    category=dpg.mvThemeCat_Nodes)
                # dpg.add_theme_color(target=dpg.mvNodesCol_MiniMapCanvas, value=(0, 0, 0, 50),
                #                     category=dpg.mvThemeCat_Nodes)
                dpg.add_theme_color(target=dpg.mvNodesCol_MiniMapCanvasOutline, value=(0, 0, 0),
                                    category=dpg.mvThemeCat_Nodes)
                # dpg.add_theme_color(target=dpg.mvNodesCol_MiniMapBackground, value=(0, 0, 0, 120),
                #                     category=dpg.mvThemeCat_Nodes)
                # dpg.add_theme_color(target=dpg.mvNodesCol_MiniMapNodeBackground, value=(128, 128, 128, 50),
                #                     category=dpg.mvThemeCat_Nodes)

            with dpg.theme_component(dpg.mvText):
                dpg.add_theme_style(target=dpg.mvStyleVar_SelectableTextAlign, x=-1, y=-1, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvMenu):
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=12, y=12, category=dpg.mvThemeCat_Core)
                # dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=12, y=12, category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_Border, value=(40, 136, 101),
                                    category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_ItemSpacing, x=15, y=15, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvCombo):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=14, y=14, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_PopupBorderSize, x=2, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_PopupRounding, x=10, category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_Border, value=(40, 136, 101),
                                    category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvInputInt):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=6, y=6, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvInputIntMulti):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=6, y=6, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvInputFloatMulti):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=6, y=6, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvDragInt):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=6, y=6, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvDragIntMulti):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=6, y=6, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvDragFloat):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=6, y=6, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvDragFloatMulti):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=6, y=6, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvInputText):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=6, y=6, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvText):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvInputFloat):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=8, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=6, y=6, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvColorEdit):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=8, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=6, y=6, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=9, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(target=dpg.mvStyleVar_WindowPadding, x=6, y=6, category=dpg.mvThemeCat_Core)
                # dpg.add_theme_style(target=dpg.mvStyleVar_ButtonTextAlign, x=6, y=6, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvCheckbox):
                dpg.add_theme_style(target=dpg.mvStyleVar_FramePadding, x=4, y=4, category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(target=dpg.mvThemeCol_CheckMark, value=(201, 99, 30),
                                    category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvSliderInt):
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=5, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvSliderFloat):
                dpg.add_theme_style(target=dpg.mvStyleVar_FrameRounding, x=5, category=dpg.mvThemeCat_Core)

        return themeTag


keytimer = time()


def key(*arg):
    global keytimer
    if keytimer < time():
        # print("asd")
        if dpg.is_key_down(dpg.mvKey_Z) and dpg.is_key_down(dpg.mvKey_Control) and dpg.is_key_down(dpg.mvKey_Shift):
            history.redo()
            keytimer = time() + 0.2
        elif dpg.is_key_down(dpg.mvKey_Z) and dpg.is_key_down(dpg.mvKey_Control):
            history.undo()
            keytimer = time() + 0.2
        elif dpg.is_key_down(dpg.mvKey_D) and dpg.get_selected_nodes(node_editor='node_editor') != []:
            move_node()
            keytimer = time() + 0.2
        elif dpg.is_key_down(dpg.mvKey_Delete) and (dpg.get_selected_nodes(node_editor='node_editor')
                                                    or dpg.get_selected_links(node_editor='node_editor')):
            if dpg.get_selected_nodes(node_editor='node_editor'):
                delete_node()
            if dpg.get_selected_links(node_editor='node_editor'):
                delink(sender='node_editor', app_data=None)
            keytimer = time() + 0.2


def move_node(*arg):
    history.add(Move_Node())


def delete_node(*arg):
    history.add(Delete_Node())


def create_node(sender, app_data, user_data, *arg):
    node = Create_Node(user_data)
    history.add(node)


def link(sender, app_data, *arg):
    connection = Create_Connection(sender, app_data)
    history.add(connection)
    connection.redo()


def delink(sender, app_data, *arg):
    connection = Delete_Connection(sender, app_data)
    history.add(connection)
    connection.redo()


def save(*arg):
    history.to_json()


def drag_n_drop(*arg):
    if dpg.get_selected_nodes(node_editor='node_editor'):
        for node in dpg.get_selected_nodes(node_editor='node_editor'):
            history.add(Drop_Node(node))


dpg.create_viewport(title='Custom Title')

window = Main_Window()
history = History()

dpg.setup_dearpygui()
dpg.show_item_registry()
dpg.show_style_editor()
dpg.show_viewport()
dpg.set_primary_window(window='main_window', value=True)

while dpg.is_dearpygui_running():
    dpg.render_dearpygui_frame()
    sleep(0.033)

dpg.destroy_context()
