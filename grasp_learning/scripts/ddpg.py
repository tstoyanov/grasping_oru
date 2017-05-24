#!/usr/bin/env python
"""
Implementation of DDPG - Deep Deterministic Policy Gradient

Algorithm and hyperparameter details can be found here:
    http://arxiv.org/pdf/1509.02971v2.pdf

The algorithm is tested on the Pendulum-v0 OpenAI gym task
and developed with tflearn + Tensorflow

Author: Patrick Emami
"""
import tflearn
import roslib

import rospy

from grasp_learning.srv import QueryNN
from grasp_learning.srv import *

from std_msgs.msg import Empty

import tensorflow as tf
import numpy as np
import os
from ou_noise import OUNoise

from replay_buffer import ReplayBuffer

# ==========================
#   Training Parameters
# ==========================
# Base learning rate for the Actor network
ACTOR_LEARNING_RATE = 0.0001
# Base learning rate for the Critic Network
CRITIC_LEARNING_RATE = 0.001
# Discount fself.actor
GAMMA = 0.99
# Soft target update param
TAU = 0.001

# ===========================
#   Utility Parameters
# ===========================
RANDOM_SEED = 1234
# Size of replay buffer
BUFFER_SIZE = 10000
MINIBATCH_SIZE = 1000

# ===========================
#   Actor and Critic DNNs
# ===========================


class ActorNetwork(object):
    """
    Input to the network is the state, output is the action
    under a deterministic policy.

    The output layer activation is a tanh to keep the action
    between -2 and 2
    """

    def __init__(self, sess, state_dim, action_dim, action_bound, learning_rate, tau):
        self.sess = sess
        self.s_dim = state_dim
        self.a_dim = action_dim
        self.action_bound = action_bound
        self.learning_rate = learning_rate
        self.tau = tau
        # Actor Network
        self.inputs, self.out, self.scaled_out = self.create_actor_network()

        self.network_params = tf.trainable_variables()

        # Target Network
        self.target_inputs, self.target_out, self.target_scaled_out = self.create_actor_network()

        self.target_network_params = tf.trainable_variables()[
            len(self.network_params):]

        # Op for periodically updating target network with online network
        # weights
        self.update_target_network_params = \
            [self.target_network_params[i].assign(tf.multiply(self.network_params[i], self.tau) +
                                                  tf.multiply(self.target_network_params[i], 1. - self.tau))
                for i in range(len(self.target_network_params))]

        # This gradient will be provided by the self.critic network
        self.action_gradient = tf.placeholder(tf.float32, [None, self.a_dim])

        # Combine the gradients here
        self.actor_gradients = tf.gradients(self.scaled_out, self.network_params, -self.action_gradient)

        # Optimization Op
        self.optimize = tf.train.AdamOptimizer(self.learning_rate).\
            apply_gradients(zip(self.actor_gradients, self.network_params))

        self.num_trainable_vars = len(
            self.network_params) + len(self.target_network_params)

    def create_actor_network(self):
        inputs = tflearn.input_data(shape=[None, self.s_dim])
        net = tflearn.fully_connected(inputs, 20, activation='relu')
        # net = tflearn.fully_connected(net, 300, activation='relu')
        # Final layer weights are init to Uniform[-3e-3, 3e-3]
        w_init = tflearn.initializations.uniform(minval=-5, maxval=5)
        out = tflearn.fully_connected(
            net, self.a_dim, activation='tanh', weights_init=w_init)
        # Scale output to -action_bound to action_bound
        scaled_out = out #tf.multiply(out, self.action_bound)
        return inputs, out, scaled_out

    def train(self, inputs, a_gradient):
        self.sess.run(self.optimize, feed_dict={
            self.inputs: inputs,
            self.action_gradient: a_gradient
        })

    def predict(self, inputs):
        return self.sess.run(self.scaled_out, feed_dict={
            self.inputs: inputs
        })

    def predict_target(self, inputs):
        return self.sess.run(self.target_scaled_out, feed_dict={
            self.target_inputs: inputs
        })

    def update_target_network(self):
        self.sess.run(self.update_target_network_params)

    def get_num_trainable_vars(self):
        return self.num_trainable_vars


class CriticNetwork(object):
    """
    Input to the network is the state and action, output is Q(s,a).
    The action must be obtained from the output of the Actor network.

    """

    def __init__(self, sess, state_dim, action_dim, learning_rate, tau, num_actor_vars):
        self.sess = sess
        self.s_dim = state_dim
        self.a_dim = action_dim
        self.learning_rate = learning_rate
        self.tau = tau

        # Create the self.critic network
        self.inputs, self.action, self.out = self.create_critic_network()

        self.network_params = tf.trainable_variables()[num_actor_vars:]

        # Target Network
        self.target_inputs, self.target_action, self.target_out = self.create_critic_network()

        self.target_network_params = tf.trainable_variables()[(len(self.network_params) + num_actor_vars):]

        # Op for periodically updating target network with online network
        # weights with regularization
        self.update_target_network_params = \
            [self.target_network_params[i].assign(tf.multiply(self.network_params[i], self.tau) + tf.multiply(self.target_network_params[i], 1. - self.tau))
                for i in range(len(self.target_network_params))]

        # Network target (y_i)
        self.predicted_q_value = tf.placeholder(tf.float32, [None, 1])

        # Define loss and optimization Op
        self.loss = tflearn.mean_square(self.predicted_q_value, self.out)
        self.optimize = tf.train.AdamOptimizer(
            self.learning_rate).minimize(self.loss)

        # Get the gradient of the net w.r.t. the action.
        # For each action in the minibatch (i.e., for each x in xs),
        # this will sum up the gradients of each self.critic output in the minibatch
        # w.r.t. that action. Each output is independent of all
        # actions except for one.
        self.action_grads = tf.gradients(self.out, self.action)

    def create_critic_network(self):
        inputs = tflearn.input_data(shape=[None, self.s_dim])
        action = tflearn.input_data(shape=[None, self.a_dim])
        net = tflearn.fully_connected(inputs, 20, activation='relu')

        # Add the action tensor in the 2nd hidden layer
        # Use two temp layers to get the corresponding weights and biases
        t1 = tflearn.fully_connected(net, 20)
        t2 = tflearn.fully_connected(action, 20)

        net = tflearn.activation(
            tf.matmul(net, t1.W) + tf.matmul(action, t2.W) + t2.b, activation='relu')

        # linear layer connected to 1 output representing Q(s,a)
        # Weights are init to Uniform[-3e-3, 3e-3]
        w_init = tflearn.initializations.uniform(minval=-5, maxval=5)
        out = tflearn.fully_connected(net, 1, weights_init=w_init)
        return inputs, action, out

    def train(self, inputs, action, predicted_q_value):
        return self.sess.run([self.out, self.optimize], feed_dict={
            self.inputs: inputs,
            self.action: action,
            self.predicted_q_value: predicted_q_value
        })

    def predict(self, inputs, action):
        return self.sess.run(self.out, feed_dict={
            self.inputs: inputs,
            self.action: action
        })

    def predict_target(self, inputs, action):
        return self.sess.run(self.target_out, feed_dict={
            self.target_inputs: inputs,
            self.target_action: action
        })

    def action_gradients(self, inputs, actions):
        return self.sess.run(self.action_grads, feed_dict={
            self.inputs: inputs,
            self.action: actions
        })

    def update_target_network(self):
        self.sess.run(self.update_target_network_params)

# ===========================
#   Tensorflow Summary Ops
# ===========================
class Policy(object):

    def __init__(self):

        num_inputs = rospy.get_param('~num_inputs', ' ')
        num_outputs = rospy.get_param('~num_outputs', ' ')
        num_rewards = rospy.get_param('~num_rewards', ' ')

        action_bound = 100000
        self.batch_size = rospy.get_param('~batch_size', '5')
        self.relative_path = rospy.get_param('~relative_path', ' ')
        self.s = rospy.Service('query_NN', QueryNN, self.handle_query_NN_)

        self.states = []
        self.actions = []

        self.policy_search_ = rospy.Service('policy_Search', PolicySearch, self.policy_search)

        self.g = tf.Graph()

        self.num_episodes = 0
        self.train = True
        self.eval_episode = False

        self.max_rew_before_convergence = 150000

        self.sess = tf.InteractiveSession(graph=self.g)
        self.exploration = OUNoise(num_outputs)


        self.actor = ActorNetwork(self.sess, num_inputs, num_outputs, action_bound,
                             ACTOR_LEARNING_RATE, TAU)

        self.critic = CriticNetwork(self.sess, num_inputs, num_outputs,
                               CRITIC_LEARNING_RATE, TAU, self.actor.get_num_trainable_vars())

        # Set up summary Ops
        summary_ops, summary_vars = self.build_summaries()

        self.sess.run(tf.global_variables_initializer())
        self.writer = tf.summary.FileWriter(self.relative_path+'/graphs', self.g)

        # Initialize target network weights
        self.actor.update_target_network()
        self.critic.update_target_network()

        # Initialize replay memory
        self.replay_buffer = ReplayBuffer(BUFFER_SIZE, RANDOM_SEED)

    def build_summaries(self):
        episode_reward = tf.Variable(0.)
        tf.summary.scalar("Reward", episode_reward)
        episode_ave_max_q = tf.Variable(0.)
        tf.summary.scalar("Qmax Value", episode_ave_max_q)

        summary_vars = [episode_reward, episode_ave_max_q]
        summary_ops = tf.summary.merge_all()

        return summary_ops, summary_vars

    def calculate_reward(self, state):

        # squared_points = np.square(np.asarray(curr_reward))
        dist_abs = np.abs(np.asarray(state))

        alpha = 1e-5#1e-17
        rollout_return = 0

        dist = sum(dist_abs)
        rollout_return = -10*dist-10*np.exp(dist) #TSV original

        return rollout_return

    def reset_episode(self):
        self.states = []
        self.actions = []
        self.exploration.reset()

    def policy_search(self, req):
        with self.g.as_default():
            self.num_episodes +=1
            if not self.eval_episode:
                num_states = len(self.states)-1
                for i in xrange(num_states):
                    r = self.calculate_reward(self.states[i+1])
                    self.replay_buffer.add(np.reshape(self.states[i], (self.actor.s_dim,)), np.reshape(self.actions[i], (self.actor.a_dim,)), r,
                            0, np.reshape(self.states[i+1], (self.actor.s_dim,)))

                r = self.calculate_reward(self.states[num_states])
                self.replay_buffer.add(np.reshape(self.states[num_states-1], (self.actor.s_dim,)), np.reshape(self.actions[num_states-1], (self.actor.a_dim,)), r,
                                1, np.reshape(self.states[num_states], (self.actor.s_dim,)))


                if self.replay_buffer.size() > MINIBATCH_SIZE:
                    s_batch, a_batch, r_batch, t_batch, s2_batch = \
                        self.replay_buffer.sample_batch(MINIBATCH_SIZE)

                    # Calculate targets
                    target_q = self.critic.predict_target(
                    s2_batch, self.actor.predict_target(s2_batch))

                    y_i = []
                    for k in xrange(MINIBATCH_SIZE):
                        if t_batch[k]:
                            y_i.append(r_batch[k])
                        else:
                            y_i.append(r_batch[k] + GAMMA * target_q[k])

                    # Update the self.critic given the targets
                    predicted_q_value, _ = self.critic.train(s_batch, a_batch, np.reshape(y_i, (MINIBATCH_SIZE, 1)))

                    # ep_ave_max_q += np.amax(predicted_q_value)

                    # Update the self.actor policy using the sampled gradient
                    a_outs = self.actor.predict(s_batch)
                    grads = self.critic.action_gradients(s_batch, a_outs)
                    self.actor.train(s_batch, grads[0])

                    # Update target networks
                    self.actor.update_target_network()
                    self.critic.update_target_network()
                    print "Networks updated"

            if self.eval_episode:
                self.eval_episode = False
                r=0
                for i in xrange(1,len(self.states)):
                    r += self.calculate_reward(self.states[i])
                print "Eval episode reward is ", r

            if self.num_episodes%10==0:
                self.eval_episode = True

            self.reset_episode()
        return PolicySearchResponse(not self.train)

                    # s = s2
                    # ep_reward += r

           #          if terminal:

           #              summary_str = sess.run(summary_ops, feed_dict={
           #                  summary_vars[0]: ep_reward,
           #                  summary_vars[1]: ep_ave_max_q / float(j)
           #              })

           #              self.writer.add_summary(summary_str, i)
           #              self.writer.flush()

           #              print '| Reward: %.2i' % int(ep_reward), " | Episode", i, \
           #                  '| Qmax: %.4f' % (ep_ave_max_q / float(j))


    def handle_query_NN_(self,req):
        with self.g.as_default():

            a = self.actor.predict(np.reshape(req.task_measures,  (1,self.actor.a_dim)))
            self.states.append(req.task_measures)
            self.actions.append(a)
            if self.train and not self.eval_episode:
            # Sample the noise

            # a = self.actor.predict(np.reshape(s, (1, 3))) + (1. / (1. + i))

                task_dynamics = a+self.exploration.noise()  #0.2*self.prev_action+0.8*(self.ffnn_mean+noise)#(mean+noise)
            else:
                task_dynamics = a


        return  task_dynamics.flatten()

    def main(self):
        rospy.spin()

# Main function.
if __name__ == '__main__':
    try:
        rospy.init_node('ddpg')
        policy = Policy()
        policy.main()
    except rospy.ROSInterruptException:
        pass47
