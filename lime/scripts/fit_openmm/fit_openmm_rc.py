# =============================================================================
# imports
# =============================================================================
import os
import sys
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
from sklearn import metrics
import tensorflow as tf
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)
tf.autograph.set_verbosity(3)
# from sklearn import metrics
import gin
import lime
import pandas as pd
import numpy as np
from openforcefield.topology import Molecule
from openforcefield.topology import Topology
from openforcefield.typing.engines.smirnoff import ForceField
FF = ForceField('test_forcefields/smirnoff99Frosst.offxml')

from openeye import oechem
ifs = oechem.oemolistream()

TRANSLATION = {
    6: 0,
    7: 1,
    8: 2,
    16: 3,
    15: 4,
    9: 5,
    17: 6,
    35: 7,
    53: 8,
    1: 9
}

ifs.open('gdb9.sdf')
mols = [next(ifs.GetOEGraphMols()) for _ in range(1000)]
# mols = ifs.GetOEGraphMols()

def data_generator():
    for mol in mols:
        try:
            mol = Molecule.from_openeye(mol)
            topology = Topology.from_molecules(mol)
            mol_sys = FF.create_openmm_system(topology)
            n_atoms = topology.n_topology_atoms
            atoms = tf.convert_to_tensor(
                    [TRANSLATION[atom._atomic_number] for atom in mol.atoms],
                    dtype=tf.float32)

            adjacency_map = np.zeros((n_atoms, n_atoms), dtype=np.float32)

            for bond in mol.bonds:
                assert bond.atom1_index < bond.atom2_index

                adjacency_map[bond.atom1_index, bond.atom2_index] = \
                    bond.bond_order

            adjacency_map = tf.convert_to_tensor(
                adjacency_map,
                dtype=tf.float32)
            
            top = Topology.from_molecules(mol)
            sys = FF.create_openmm_system(top)

            angles = tf.convert_to_tensor(
                    [[x[0], x[1], x[2], 
                        (x[3]._value - 1.965) / 0.237, 
                        (x[4]._value - 507.28) / 396.80] for x in\
                    [sys.getForces(
                        )[0].getAngleParameters(idx)\
                        for idx in range(sys.getForces(
                            )[0].getNumAngles())]],
                    dtype=tf.float32)
            

            bonds = tf.convert_to_tensor([[x[0], x[1], 
                        (x[2]._value - 0.126) / 0.0212, 
                        (x[3]._value - 274856) / 12213.203]  for x in\
                    [sys.getForces(
                        )[1].getBondParameters(idx)\
                        for idx in range(sys.getForces(
                            )[1].getNumBonds())]],
                    dtype=tf.float32)


            torsions = tf.convert_to_tensor([
                [x[0], x[1], x[2], x[3], x[4], x[5]._value, x[6]._value] for x in\
                    [sys.getForces(
                        )[3].getTorsionParameters(idx)\
                        for idx in range(sys.getForces(
                            )[3].getNumTorsions())]],
                    dtype=tf.float32)


            particle_params = tf.convert_to_tensor([[
                    (x[0]._value - 0.00195) / 0.269,
                    (x[1]._value - 0.276) / 0.0654,
                    (x[2]._value - 0.285) / 0.285
                    ] for x in\
                    [sys.getForces(
                        )[2].getParticleParameters(idx)\
                        for idx in range(sys.getForces(
                            )[2].getNumParticles())]])
            
            
            yield atoms, adjacency_map, angles, bonds, torsions, particle_params
        
        except:
            pass

'''
angles_ = tf.constant(-1, shape=[1, 5], dtype=tf.float32)
bonds_ = tf.constant(-1, shape=[1, 4], dtype=tf.float32)
particle_params_ = tf.constant(-1, shape=[1, 3], dtype=tf.float32)


idx = 0
for atoms, adjacency_map, angles, bonds, torsions, particle_params in data_generator():
    idx += 1
    bonds_ = tf.concat([bonds_, bonds], axis=0)
    angles_ = tf.concat([angles_, angles], axis=0)
    particle_params_ = tf.concat([particle_params_, particle_params], axis=0)
    if idx > 100:
        break
    print(idx)

angles_ = angles_[1:]
bonds_ = bonds[1:]
particle_params_ = particle_params_[1:]

print(angles_)
print(bonds_)
print(particle_params_)

bond_length_moments = tf.nn.moments(bonds_[:, 2], [0])
bond_k_moments = tf.nn.moments(bonds_[:, 3], [0])
angle_moments = tf.nn.moments(angles_[:, 3], [0])
angle_k_moments = tf.nn.moments(angles_[:, 4], [0])

q_moments = tf.nn.moments(particle_params_[:, 0], [0])
sigma_moments = tf.nn.moments(particle_params_[:, 1], [0])
epsilon_moments = tf.nn.moments(particle_params_[:, 2], [0])

print(bond_length_moments[0].numpy(),
        tf.math.sqrt(bond_length_moments[1]).numpy())

print(bond_k_moments[0].numpy(), 
        tf.math.sqrt(bond_k_moments[1]).numpy())

print(angle_moments[0].numpy(),
        tf.math.sqrt(angle_moments[1]).numpy())

print(angle_k_moments[0].numpy(),
        tf.math.sqrt(angle_k_moments[1]).numpy())

print(q_moments[0].numpy(),
        tf.math.sqrt(q_moments[1]).numpy())

print(sigma_moments[0].numpy(),
        tf.math.sqrt(sigma_moments[1]).numpy())

print(epsilon_moments[0].numpy(),
    tf.math.sqrt(epsilon_moments[1]).numpy())


'''
ds = tf.data.Dataset.from_generator(
    data_generator,
    (
        tf.float32, 
        tf.float32, 
        tf.float32,
        tf.float32,
        tf.float32,
        tf.float32))

ds = ds.map(
    lambda atoms, adjacency_map, angles, bonds, torsions, particle_params:\
        tf.py_function(
            lambda atoms, adjacency_map, angles, bonds, torsions, particle_params:\
        [
            gin.probabilistic.featurization.featurize_atoms(
                tf.cast(atoms, dtype=tf.int64), adjacency_map),
            adjacency_map,
            angles,
            bonds,
            torsions,
            particle_params
        ],
        [atoms, adjacency_map, angles, bonds, torsions, particle_params],
        [tf.float32, tf.float32, tf.float32, tf.float32, tf.float32,
            tf.float32])).cache('ds')

n_te = 100

ds_tr = ds.skip(2 * n_te).take(8 * n_te)
ds_te = ds.take(n_te)
ds_vl = ds.skip(n_te).take(n_te)


config_space = {
    'D_V': [16, 32, 64, 128, 256],
    'D_E': [16, 32, 64, 128, 256],
    'D_U': [16, 32, 64, 128, 256],

    'phi_e_0': [32, 64, 128],
    'phi_e_a_0': ['elu', 'relu', 'leaky_relu', 'tanh', 'sigmoid'],
    'phi_e_a_1': ['elu', 'relu', 'leaky_relu', 'tanh', 'sigmoid'],

    'phi_v_0': [32, 64, 128],
    'phi_v_a_0': ['elu', 'relu', 'leaky_relu', 'tanh', 'sigmoid'],
    'phi_v_a_1': ['elu', 'relu', 'leaky_relu', 'tanh', 'sigmoid'],

    'phi_u_0': [32, 64, 128],
    'phi_u_a_0': ['elu', 'relu', 'leaky_relu', 'tanh', 'sigmoid'],
    'phi_u_a_1': ['elu', 'relu', 'leaky_relu', 'tanh', 'sigmoid'],

    'f_r_0': [32, 64, 128],
    'f_r_1': [32, 64, 128],
    'f_r_a_0': ['elu', 'relu', 'leaky_relu', 'tanh', 'sigmoid'],
    'f_r_a_1': ['elu', 'relu', 'leaky_relu', 'tanh', 'sigmoid'],

    'learning_rate': [1e-5, 1e-4, 1e-3]

}

def init(point):
    global gn
    global opt

    class f_v(tf.keras.Model):
        def __init__(self, units=point['D_V']):
            super(f_v, self).__init__()
            self.d = tf.keras.layers.Dense(units)

        @tf.function
        def call(self, x):
            '''
            x = tf.one_hot(
                tf.cast(
                    x,
                    tf.int64),
                8)
            

            x.set_shape([None, 8])
            '''
            return self.d(x)

    class f_r(tf.keras.Model):
        """ Readout function
        """
        def __init__(self, units=point['f_r_0'], f_r_a=point['f_r_a_0']):
            super(f_r, self).__init__()

            self.d_q_0 = tf.keras.layers.Dense(units, activation='tanh')
            self.d_q_1 = tf.keras.layers.Dense(1)

            self.d_sigma_0 = tf.keras.layers.Dense(units, activation='tanh')
            self.d_sigma_1 = tf.keras.layers.Dense(1)

            self.d_epislon_0 = tf.keras.layers.Dense(units, activation='tanh')
            self.d_epsilon_1 = tf.keras.layers.Dense(1)

            self.d_e_1 = tf.keras.layers.Dense(2,
                kernel_initializer='random_uniform')

            self.d_e_0 = tf.keras.layers.Dense(units, activation='tanh')


            self.d_a_1 = tf.keras.layers.Dense(2,
                kernel_initializer='random_uniform')

            self.d_a_0 = tf.keras.layers.Dense(units, activation='tanh')

            self.d_e0_0 = lime.nets.for_gn.ConcatenateThenFullyConnect((units,
              'relu', units, 'relu'))

            self.d_e0_1 = tf.keras.layers.Dense(1)

            self.units = units
            self.d_v = point['D_V']
            self.d_e = point['D_E']
            self.d_a = point['D_E']
            self.d_t = point['D_E']
            self.d_u = point['D_U']

        # @tf.function
        def call(self, 
                 h_e, h_v, h_u,
                 h_e_history, h_v_history, h_u_history,
                 atom_in_mol, bond_in_mol, bond_idxs, angle_idxs):
 
            h_v_history.set_shape([None, 6, self.d_v])

            h_v = tf.reshape(
                h_v_history,
               [-1, 6 * self.d_v])

            h_e = tf.math.add(
                tf.gather(
                    h_v,
                    bond_idxs[:, 0]),
                tf.gather(
                    h_v,
                    bond_idxs[:, 1]))

            h_a = tf.concat(
                [
                    tf.gather(
                        h_v,
                        angle_idxs[:, 1]),
                    tf.math.add(
                        tf.gather(
                            h_v,
                            angle_idxs[:, 0]),
                        tf.gather(
                            h_v,
                            angle_idxs[:, 2]))
                        
                ],
                axis=1)

            y_e = self.d_e_1(
                    self.d_e_0(
                        h_e))

            y_a = self.d_a_1(
                    self.d_a_0(
                        h_a))

            # (n_atoms, n_atoms)
            q = tf.squeeze(
                self.d_q_1(
                    self.d_q_0(
                        h_v)))

            # (n_atoms, n_atoms)
            sigma = tf.squeeze(
                self.d_sigma_1(
                    self.d_sigma_0(
                        h_v)))

            # (n_atoms, n_atoms)
            epsilon = tf.squeeze(
                self.d_epsilon_1(
                    self.d_epislon_0(
                        h_v)))

            return y_e, y_a, q, sigma, epsilon
        
    gn = gin.probabilistic.gn_plus.GraphNet(
            f_e=lime.nets.for_gn.ConcatenateThenFullyConnect(
                (point['D_E'], 'elu', point['D_E'], 'tanh')),
            f_v=f_v(),
            f_u=(lambda atoms, adjacency_map, batched_attr_in_mol: \
                tf.tile(
                    tf.zeros((1, point['D_U'])),
                    [
                         tf.math.count_nonzero(batched_attr_in_mol),
                         1
                    ]
                )),
            phi_e=lime.nets.for_gn.ConcatenateThenFullyConnect(
                (point['phi_e_0'], point['phi_e_a_0'], point['D_E'],
                point['phi_e_a_1'])),
            phi_v=lime.nets.for_gn.ConcatenateThenFullyConnect(
                (point['phi_v_0'], point['phi_v_a_0'], point['D_V'],
                point['phi_v_a_1'])),

            phi_u=lime.nets.for_gn.ConcatenateThenFullyConnect(
                (point['phi_u_0'], point['phi_u_a_0'], point['D_U'],
                point['phi_v_a_1'])),
            f_r=f_r(),
            repeat=5)

    opt = tf.keras.optimizers.Adam(1e-5)


def obj_fn(point):
    point = dict(zip(config_space.keys(), point))
    init(point)

    for dummy_idx in range(10):
        idx = 0
        g = []
        for atoms, adjacency_map, angles, bonds, torsions, particle_params in ds:
            
            '''
            bond_idxs, angle_idxs, torsion_idxs = gin.probabilistic.gn_hyper\
                            .get_geometric_idxs(atoms, adjacency_map)
            '''

            bond_idxs = tf.cast(
                bonds[:, :2],
                tf.int64)

            angle_idxs = tf.cast(
                angles[:, :3],
                tf.int64)

            with tf.GradientTape() as tape:
                [
                    y_e,
                    y_a,
                    q, 
                    sigma, 
                    epsilon
                ] = gn(
                        atoms, 
                        adjacency_map, 
                        bond_idxs=bond_idxs,
                        angle_idxs=angle_idxs)
                

                angle_loss = tf.keras.losses.MAE(
                    tf.reshape(angles[:, 3:], [-1]),
                    tf.reshape(tf.math.exp(y_a), [-1]))

                bond_loss = tf.keras.losses.MAE(
                    tf.reshape(bonds[:, 2:], [-1]),
                    tf.reshape(tf.math.exp(y_e), [-1]))

                atom_loss = tf.keras.losses.MAE(
                    tf.reshape(
                                tf.stack(
                                    [
                                        q,
                                        sigma,
                                        epsilon
                                    ],
                                    axis=1),
                                [-1]),
                            tf.reshape(
                                particle_params,
                                [-1]))

                loss = atom_loss + bond_loss + angle_loss
                
            g.append(tape.gradient(loss, gn.variables))
            idx += 1
            if idx % 32 == 0:
                for g_ in g:
                    opt.apply_gradients(zip(g_, gn.variables))

                idx = 0
                g = []

    atom_true_tr = tf.constant([[-1, -1, -1]], dtype=tf.float32)
    bond_true_tr = tf.constant([[-1, -1]], dtype=tf.float32)
    angle_true_tr = tf.constant([[-1, -1]], dtype=tf.float32)
    atom_true_te = tf.constant([[-1, -1, -1]], dtype=tf.float32)
    bond_true_te = tf.constant([[-1, -1]], dtype=tf.float32)
    angle_true_te = tf.constant([[-1, -1]], dtype=tf.float32)
    atom_true_vl = tf.constant([[-1, -1, -1]], dtype=tf.float32)
    bond_true_vl = tf.constant([[-1, -1]], dtype=tf.float32)
    angle_true_vl = tf.constant([[-1, -1]], dtype=tf.float32)

    atom_pred_tr = tf.constant([[-1, -1, -1]], dtype=tf.float32)
    bond_pred_tr = tf.constant([[-1, -1]], dtype=tf.float32)
    angle_pred_tr = tf.constant([[-1, -1]], dtype=tf.float32)
    atom_pred_te = tf.constant([[-1, -1, -1]], dtype=tf.float32)
    bond_pred_te = tf.constant([[-1, -1]], dtype=tf.float32)
    angle_pred_te = tf.constant([[-1, -1]], dtype=tf.float32)
    atom_pred_vl = tf.constant([[-1, -1, -1]], dtype=tf.float32)
    bond_pred_vl = tf.constant([[-1, -1]], dtype=tf.float32)
    angle_pred_vl = tf.constant([[-1, -1]], dtype=tf.float32)

    for atoms, adjacency_map, angles, bonds, torsions, particle_params in ds_tr:

        '''
        bond_idxs, angle_idxs, torsion_idxs = gin.probabilistic.gn_hyper\
                        .get_geometric_idxs(atoms, adjacency_map)
        '''

        bond_idxs = tf.cast(
            bonds[:, :2],
            tf.int64)

        angle_idxs = tf.cast(
            angles[:, :3],
            tf.int64)

 
        [
            y_e,
            y_a,
            q, 
            sigma, 
            epsilon
        ] = gn(
                atoms, 
                adjacency_map, 
                bond_idxs=bond_idxs,
                angle_idxs=angle_idxs)
        
        bond_hat = tf.math.exp(y_e)
        atom_hat = tf.stack([q, sigma, epsilon], axis=1)
        angle_hat = tf.math.exp(y_a)

        bond_true_tr = tf.concat([bond_true_tr, bonds[:, 2:]], axis=0)
        atom_true_tr = tf.concat([atom_true_tr, particle_params], axis=0)
        angle_true_tr = tf.concat([angle_true_tr, angles[:, 3:]], axis=0)

        bond_pred_tr = tf.concat([bond_pred_tr, bond_hat], axis=0)
        atom_pred_tr = tf.concat([atom_pred_tr, atom_hat], axis=0)
        angle_pred_tr = tf.concat([angle_pred_tr, angle_hat], axis=0)

    for atoms, adjacency_map, angles, bonds, torsions, particle_params in ds_te:
        ''' 
        bond_idxs, angle_idxs, torsion_idxs = gin.probabilistic.gn_hyper\
                        .get_geometric_idxs(atoms, adjacency_map)
        '''

        bond_idxs = tf.cast(
            bonds[:, :2],
            tf.int64)

        angle_idxs = tf.cast(
            angles[:, :3],
            tf.int64)


        [
            y_e, 
            y_a,
            q, 
            sigma, 
            epsilon
        ] = gn(atoms, adjacency_map, bond_idxs=bond_idxs,
                angle_idxs = angle_idxs)

        bond_hat = tf.math.exp(y_e)
        atom_hat = tf.stack([q, sigma, epsilon], axis=1)
        angle_hat = tf.math.exp(y_a)

        bond_true_te = tf.concat([bond_true_te, bonds[:, 2:]], axis=0)
        atom_true_te = tf.concat([atom_true_te, particle_params], axis=0)
        angle_true_te = tf.concat([angle_true_te, angles[:, 3:]], axis=0)

        bond_pred_te = tf.concat([bond_pred_te, bond_hat], axis=0)
        atom_pred_te = tf.concat([atom_pred_te, atom_hat], axis=0)
        angle_pred_te = tf.concat([angle_pred_te, angle_hat], axis=0)

    for atoms, adjacency_map, angles, bonds, torsions, particle_params in ds_vl:
        ''' 
        bond_idxs, angle_idxs, torsion_idxs = gin.probabilistic.gn_hyper\
                        .get_geometric_idxs(atoms, adjacency_map)
        '''


        bond_idxs = tf.cast(
            bonds[:, :2],
            tf.int64)

        angle_idxs = tf.cast(
            angles[:, :3],
            tf.int64)

 
        [
            y_e, 
            y_a,
            q, 
            sigma, 
            epsilon
        ] = gn(atoms, adjacency_map, bond_idxs=bond_idxs,
                angle_idxs=angle_idxs)

        bond_hat = tf.math.exp(y_e)
        atom_hat = tf.stack([q, sigma, epsilon], axis=1)
        angle_hat = tf.math.exp(y_a)

        bond_true_vl = tf.concat([bond_true_vl, bonds[:, 2:]], axis=0)
        atom_true_vl = tf.concat([atom_true_vl, particle_params], axis=0)
        angle_true_vl = tf.concat([angle_true_vl, angles[:, 3:]], axis=0)

        bond_pred_vl = tf.concat([bond_pred_vl, bond_hat], axis=0)
        atom_pred_vl = tf.concat([atom_pred_vl, atom_hat], axis=0)
        angle_pred_vl = tf.concat([angle_pred_vl, angle_hat], axis=0)

    print(point)

    print('bond l tr')
    print(metrics.r2_score(bond_true_tr[1:, 0], bond_pred_tr[1:, 0]))
    print('bond k tr')
    print(metrics.r2_score(bond_true_tr[1:, 1], bond_pred_tr[1:, 1]))
    print('angle l tr')
    print(metrics.r2_score(angle_true_tr[1:, 0], angle_pred_tr[1:, 0]))
    print('angle k tr')
    print(metrics.r2_score(angle_true_tr[1:, 1], angle_pred_tr[1:, 1]))
    print('q tr')
    print(metrics.r2_score(atom_true_tr[1:, 0], atom_pred_tr[1:, 0]))
    print('sigma tr')
    print(metrics.r2_score(atom_true_tr[1:, 1], atom_pred_tr[1:, 1]))
    print('epsilon tr')
    print(metrics.r2_score(atom_true_tr[1:, 2], atom_pred_tr[1:, 2]))

    print('bond l te')
    print(metrics.r2_score(bond_true_te[1:, 0], bond_pred_te[1:, 0]))
    print('bond k te')
    print(metrics.r2_score(bond_true_te[1:, 1], bond_pred_te[1:, 1]))
    print('angle l te')
    print(metrics.r2_score(angle_true_te[1:, 0], angle_pred_te[1:, 0]))
    print('angle k te')
    print(metrics.r2_score(angle_true_te[1:, 1], angle_pred_te[1:, 1]))
    print('q te')
    print(metrics.r2_score(atom_true_te[1:, 0], atom_pred_te[1:, 0]))
    print('sigma te')
    print(metrics.r2_score(atom_true_te[1:, 1], atom_pred_te[1:, 1]))
    print('epsilon te')
    print(metrics.r2_score(atom_true_te[1:, 2], atom_pred_te[1:, 2]))

    print('bond l vl')
    print(metrics.r2_score(bond_true_vl[1:, 0], bond_pred_vl[1:, 0]))
    print('bond k vl')
    print(metrics.r2_score(bond_true_vl[1:, 1], bond_pred_vl[1:, 1]))
    print('angle l vl')
    print(metrics.r2_score(angle_true_vl[1:, 0], angle_pred_vl[1:, 0]))
    print('angle k vl')
    print(metrics.r2_score(angle_true_vl[1:, 1], angle_pred_vl[1:, 1]))   
    print('q vl')
    print(metrics.r2_score(atom_true_vl[1:, 0], atom_pred_vl[1:, 0]))
    print('sigma vl')
    print(metrics.r2_score(atom_true_vl[1:, 1], atom_pred_vl[1:, 1]))
    print('epsilon vl')
    print(metrics.r2_score(atom_true_vl[1:, 2], atom_pred_vl[1:, 2]))
    print('', flush=True)


    np.save('angle_l_te_true', angle_true_te[1:, 0].numpy())
    np.save('angle_k_te_true', angle_true_te[1:, 1].numpy())
    np.save('angle_l_te_pred', angle_pred_te[1:, 0].numpy())
    np.save('angle_k_te_pred', angle_pred_te[1:, 1].numpy())
    
    return metrics.r2_score(atom_true_vl[1:, 2], atom_pred_vl[1:, 2])

lime.optimize.dummy.optimize(obj_fn, config_space.values(), 1)
