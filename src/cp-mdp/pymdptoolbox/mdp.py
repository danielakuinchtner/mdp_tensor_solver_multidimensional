# -*- coding: utf-8 -*-
"""
THIS IS A PYMDPTOOLBOX IMPLEMENTATION MODIFIED BY DANIELA KUINCHTNER



Markov Decision Process (MDP) Toolbox: ``mdp`` module
=====================================================

The ``mdp`` module provides classes for the resolution of discrete-time Markov
Decision Processes.

Available classes
-----------------
:class:`~mdptoolbox.mdp.MDP`
    Base Markov decision process class
:class:`~mdptoolbox.mdp.CpMdpValueIteration`
    CP-MDP Value Iteration tensor-based algorithm
:class:`~mdptoolbox.mdp.CpMdpValueIterationGS`
    CP-MDP Value Iteration Gauss-Seidel tensor-based algorithm
:class:`~mdptoolbox.mdp.CpMdpPolicyIteration`
    CP-MDP Policy Iteration tensor-based algorithm


"""

# Copyright (c) 2011-2015 Steven A. W. Cordwell
# Copyright (c) 2009 INRA
#
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions and the following disclaimer in the documentation
#     and/or other materials provided with the distribution.
#   * Neither the name of the <ORGANIZATION> nor the names of its contributors
#     may be used to endorse or promote products derived from this software
#     without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import math as _math
import time as _time
import numpy as _np
import scipy.sparse as _sp

_MSG_STOP_MAX_ITER = "Iterating stopped due to maximum number of iterations " \
                     "condition."
_MSG_STOP_EPSILON_OPTIMAL_POLICY = "Iterating stopped, epsilon-optimal " \
                                   "policy found."
_MSG_STOP_EPSILON_OPTIMAL_VALUE = "Iterating stopped, epsilon-optimal value " \
                                  "function found."
_MSG_STOP_UNCHANGING_POLICY = "Iterating stopped, unchanging policy found."


def _computeDimensions(transition):
    A = len(transition)

    try:
        if transition.ndim == 3:
            S = transition.shape[1]
        else:
            S = transition[0].shape[0]
    except AttributeError:
        S = transition[0].shape[0]

    return S, A

def getSpan(array):
    """Return the span of `array`

    span(array) = max array(s) - min array(s)

    """
    return array.max() - array.min()


def _printVerbosity(iteration, variation):
    if isinstance(variation, float):
        print("{:>10}{:>12f}".format(iteration, variation))
    elif isinstance(variation, int):
        print("{:>10}{:>12d}".format(iteration, variation))
    else:
        print("{:>10}{:>12}".format(iteration, variation))


class MDP(object):

    def __init__(self, shape, terminals, obstacles, succ_s, probability_s, R, states, discount,
                 epsilon, max_iter):
        # Initialize an MDP based on the input parameters.

        # if the discount is None then the algorithm is assumed to not use it
        # in its computations
        if discount is not None:
            self.discount = float(discount)
            assert 0.0 < self.discount <= 1.0, (
                "Discount rate must be in ]0; 1]"
            )

        # if the max_iter is None then the algorithm is assumed to not use it
        # in its computations
        if max_iter is not None:
            self.max_iter = int(max_iter)
            assert self.max_iter > 0, (
                "The maximum number of iterations must be greater than 0."
            )

        # check that epsilon is something sane
        if epsilon is not None:
            self.epsilon = float(epsilon)
            assert self.epsilon > 0, "Epsilon must be greater than 0."

        self.S, self.A = _computeDimensions(succ_s)
        self.shape = shape
        self.probabilities_s = probability_s
        self.succ_s = succ_s
        self.obstacles = obstacles
        self.terminals = terminals
        self.states = states
        self.R = self._computeReward(R, succ_s)
        self.split_succ_s = []
        self.split_probability = []
        for aa in range(self.A):
            self.split_succ_s.append(_np.split(self.succ_s[aa], self.states))
            self.split_probability.append(_np.split(self.probabilities_s[aa], self.states))


        # the verbosity is by default turned off
        self.verbose = False
        # Initially the time taken to perform the computations is set to None
        self.time = None
        # set the initial iteration count to zero
        self.iter = 0
        # V should be stored as a vector ie shape of (S,) or (1, S)
        self.V = None
        # policy can also be stored as a vector
        self.policy = None


    def _bellmanOperator(self, V=None):
        # Apply the Bellman operator on the value function.
        #
        # Updates the value function and the Vprev-improving policy.
        #
        # Returns: (policy, value), tuple of new policy and its value
        #
        # If V hasn't been sent into the method, then we assume to be working
        # on the objects V attribute
        if V is None:
            # this V should be a reference to the data rather than a copy
            V = self.V
        else:
            # make sure the user supplied V is of the right shape
            try:
                assert V.shape in ((self.states,), (1, self.states)), "V is not the right shape (Bellman operator)."
            except AttributeError:
                raise TypeError("V must be a numpy array or matrix.")


        Q = _np.empty((self.A, self.states))
        V = _np.asarray(V)

        for a in range(self.A):
            Q[a] = [(self.R[a][s1] + self.discount * _np.dot(self.split_probability[a][s1], V[self.split_succ_s[a][s1]]))
                   for s1 in range(self.states)]


        Q = _np.asarray(Q)

        return Q.argmax(axis=0), Q.max(axis=0)


    def _computeReward(self, reward, transition):
        # Compute the reward for the system in one state chosing an action.
        # Arguments
        # Let S = number of states, A = number of actions
        try:
            if reward.ndim == 1:
                return self._computeVectorReward(reward)
            elif reward.ndim == 2:
                return self._computeArrayReward(reward)
            else:
                r = tuple(map(self._computeMatrixReward, reward, transition))
                return r
        except (AttributeError, ValueError):
            if len(reward) == self.A:
                r = tuple(map(self._computeMatrixReward, reward, transition))
                return r
            else:
                return self._computeVectorReward(reward)

    def _computeVectorReward(self, reward):
        if _sp.issparse(reward):
            raise NotImplementedError
        else:
            r = _np.array(reward).reshape(self.states)  # .reshape(self.S)
            # print(self.S)
            return tuple(r for a in range(self.A))

    def _computeArrayReward(self, reward):
        if _sp.issparse(reward):
            raise NotImplementedError
        else:
            def func(x):
                return _np.array(x).reshape(self.states)  # reshape(self.S)

            return tuple(func(reward[:, a]) for a in range(self.A))

    def _computeMatrixReward(self, reward, transition):
        if _sp.issparse(reward):
            # An approach like this might be more memory efficeint
            # reward.data = reward.data * transition[reward.nonzero()]
            # return reward.sum(1).A.reshape(self.S)
            # but doesn't work as it is.
            return reward.multiply(transition).sum(1).A.reshape(self.states)  # reshape(self.S)
        elif _sp.issparse(transition):
            return transition.multiply(reward).sum(1).A.reshape(self.states)  # reshape(self.S)
        else:
            return _np.multiply(transition, reward).sum(1).reshape(self.states)  # reshape(self.S)

    def _startRun(self):
        if self.verbose:
            _printVerbosity('Iteration', 'Variation')

        self.time = _time.time()

    def _endRun(self):
        # store value and policy as tuples
        #self.V = tuple(self.V.tolist())

        try:
            self.policy = tuple(self.policy.tolist())
        except AttributeError:
            self.policy = tuple(self.policy)

        self.time = _time.time() - self.time

    def run(self):
        """Raises error because child classes should implement this function.
        """
        raise NotImplementedError("You should create a run() method.")




class CpMdpPolicyIteration(MDP):

    """A discounted MDP solver using the compact tensor-based policy iteration algorithm (CP-MDP-PI).

    Arguments
    ---------

    reward : array
        Reward matrices or vectors. See the documentation for the ``MDP`` class
        for details.
    discount : float
        Discount factor. See the documentation for the ``MDP`` class for
        details.
    policy0 : array, optional
        Starting policy.
    max_iter : int, optional
        Maximum number of iterations. See the documentation for the ``MDP``
        class for details. Default is 1000.


    Data Attributes
    ---------------
    V : tuple
        value function
    policy : tuple
        optimal policy
    iter : int
        number of done iterations
    time : float
        used CPU time

    Notes
    -----
    In verbose mode, at each iteration, displays the number
    of differents actions between policy n-1 and n

    """

    def __init__(self, shape, terminals, obstacles, succ_s, probability_s, R, states, discount, epsilon, policy0=None,
                 max_iter=1000):
        # Initialise a policy iteration MDP.

        # Set up the MDP, but don't need to worry about epsilon values
        MDP.__init__(self, shape, terminals, obstacles, succ_s, probability_s, R, states, discount, epsilon, max_iter)

        # Check if the user has supplied an initial policy. If not make one.
        if policy0 is None:
            # Initialise the policy to the one which maximises the expected
            # immediate reward
            null = _np.zeros(self.states)
            self.policy, null = self._bellmanOperator(null)

            del null
        else:
            # Use the policy that the user supplied
            # Make sure it is a numpy array
            policy0 = _np.array(policy0)
            # Make sure the policy is the right size and shape
            assert policy0.shape in ((self.S, ), (self.S, 1), (1, self.S)), \
                "'policy0' must a vector with length S."
            # reshape the policy to be a vector
            policy0 = policy0.reshape(self.S)
            # The policy can only contain integers between 0 and S-1
            msg = "'policy0' must be a vector of integers between 0 and S-1."
            assert not _np.mod(policy0, 1).any(), msg
            assert (policy0 >= 0).all(), msg
            assert (policy0 < self.S).all(), msg
            self.policy = policy0
        # set the initial values to zero
        self.V = _np.zeros(self.states)
        # Do some setup depending on the evaluation type


    def _computePpolicyPRpolicy(self):
        # Compute the compact transition matrix and the reward matrix for a policy.

        Ppolicy_s = _np.zeros((self.states*(self.A-1)))
        Ppolicy_p = _np.zeros((self.states*(self.A-1)))

        Rpolicy = _np.zeros(self.states)

        split_Ppolicy_p = (_np.split(Ppolicy_p, self.states))
        split_Ppolicy_s = (_np.split(Ppolicy_s, self.states))

        split_Ppolicy_s = _np.asarray(split_Ppolicy_s)
        split_Ppolicy_p = _np.asarray(split_Ppolicy_p)
        self.split_succ_s = _np.asarray(self.split_succ_s)
        self.split_probability = _np.asarray(self.split_probability)

        for aa in range(self.A):  # avoid looping over S
            # the rows that use action a.

            ind = (self.policy == aa).nonzero()[0]

            # if no rows use action a, then no need to assign this
            if ind.size > 0:
                split_Ppolicy_s[ind] = self.split_succ_s[aa][ind]
                split_Ppolicy_p[ind] = self.split_probability[aa][ind]
                Rpolicy[ind] = self.R[aa][ind]

        if type(self.R) is _sp.csr_matrix:
            Rpolicy = _sp.csr_matrix(Rpolicy)

        return Rpolicy, split_Ppolicy_s, split_Ppolicy_p

    def _evalPolicyIterative(self, V0=0, epsilon=0.0001, max_iter=100):
        # Evaluate a policy using iteration.
        #
        # Arguments
        # ---------
        # Let S = number of states, A = number of actions
        # discount  = discount rate in ]0; 1[
        # policy(S) = a policy
        # V0(S)     = starting value function, optional (default : zeros(S,1))
        # epsilon   = epsilon-optimal policy search, upper than 0,
        #    optional (default : 0.0001)
        # max_iter  = maximum number of iteration to be done, upper than 0,
        #    optional (default : 10000)
        #
        # Evaluation
        # ----------
        # Vpolicy(S) = value function, associated to a specific policy
        #
        # Notes
        # -----
        # In verbose mode, at each iteration, displays the condition which
        # stopped iterations: epsilon-optimum value function found or maximum
        # number of iterations reached.
        #
        try:
            assert V0.shape in ((self.states, ), (self.states, 1), (1, self.states)), \
                "'V0' must be a vector of length S."
            policy_V = _np.array(V0).reshape(self.states)
            #print("*******", policy_V)
        except AttributeError:
            if V0 == 0:
                policy_V = _np.zeros(self.states)
            else:
                policy_V = _np.array(V0).reshape(self.states)

        policy_R, succ_s, probabilities_s = self._computePpolicyPRpolicy()

        if self.verbose:
            _printVerbosity("Iteration", "V variation")

        itr = 0
        done = False

        while not done:
            itr += 1

            Vprev = policy_V
            Vprev = _np.array(Vprev)
            succ_s = _np.asarray(succ_s, dtype=_np.int32)

            policy_V = [(policy_R[s1] + self.discount *
                _np.dot(probabilities_s[s1], Vprev[succ_s[s1]]))
                for s1 in range(self.states)]

            variation = _np.absolute(policy_V - Vprev).max()

            if self.verbose:
                _printVerbosity(itr, variation)

            # ensure |Vn - Vpolicy| < epsilon
            if variation < ((1 - self.discount) / self.discount) * epsilon:

                done = True
                if self.verbose:
                    print(_MSG_STOP_EPSILON_OPTIMAL_VALUE)
                break

            elif itr == max_iter:
                done = True
                if self.verbose:
                    print(_MSG_STOP_MAX_ITER)
                break


        self.V = policy_V


    def run(self):
        # Run the policy iteration algorithm.
        self._startRun()

        while True:
            self.iter += 1
            # these _evalPolicy* functions will update the classes value
            # attribute

            self._evalPolicyIterative()

            # This should update the classes policy attribute but leave the
            # value alone
            policy_next, null = self._bellmanOperator()
            del null
            # calculate in how many places does the old policy disagree with
            # the new policy
            n_different = (policy_next != self.policy).sum()
            # if verbose then continue printing a table
            if self.verbose:
                _printVerbosity(self.iter, n_different)
            # Once the policy is unchanging of the maximum number of
            # of iterations has been reached then stop
            if n_different == 0:
                if self.verbose:
                    print(_MSG_STOP_UNCHANGING_POLICY)
                break
            elif self.iter == self.max_iter:
                if self.verbose:
                    print(_MSG_STOP_MAX_ITER)
                break
            else:
                self.policy = policy_next


        self._endRun()



class CpMdpValueIteration(MDP):

    def __init__(self, transitions, reward, shape, succ_s, discount, epsilon=0.01,
                 max_iter=1000, initial_value=0):
        # Initialise a value iteration MDP.

        MDP.__init__(self, transitions, reward, shape, succ_s, discount, epsilon, max_iter)
        self.iterations_list = []
        self.v_list = []
        # initialization of optional arguments
        if initial_value == 0:
            self.V = _np.zeros(self.states)
        else:
            assert len(initial_value) == self.states, "The initial value must be " \
                                                      "a vector of length S."
            self.V = _np.array(initial_value).reshape(self.states)  # reshape(self.S)
        if self.discount < 1:
            # compute a bound for the number of iterations and update the
            # stored value of self.max_iter
            self._boundIter(epsilon)
            # computation of threshold of variation for V for an epsilon-
            # optimal policy
            self.thresh = epsilon * (1 - self.discount) / self.discount
        else:  # discount == 1
            # threshold of variation for V for an epsilon-optimal policy
            self.thresh = epsilon

    def _boundIter(self, epsilon):

        k = 0
        h = _np.zeros(self.states)

        k = 1 - h.sum()
        Vprev = self.V

        null, value = self._bellmanOperator()

        # p 201, Proposition 6.6.5
        span = getSpan(value - Vprev)
        max_iter = (_math.log((epsilon * (1 - self.discount) / self.discount) /
                              span) / _math.log(self.discount * k))

        self.max_iter = int(_math.ceil(max_iter))

    def run(self):
        # Run the value iteration algorithm.
        self._startRun()

        while True:
            self.iter += 1

            Vprev = self.V.copy()

            # Bellman Operator: compute policy and value functions
            self.policy, self.V = self._bellmanOperator()

            # The values, based on Q. For the function "max()": the option
            # "axis" means the axis along which to operate. In this case it
            # finds the maximum of the the rows. (Operates along the columns?)
            variation = getSpan(self.V - Vprev)
            self.iterations_list.append(variation)
            self.v_list.append(self.V.copy())
            if self.verbose:
                _printVerbosity(self.iter, variation)

            if variation < self.thresh:
                if self.verbose:
                    print(_MSG_STOP_EPSILON_OPTIMAL_POLICY)
                break
            elif self.iter == self.max_iter:
                if self.verbose:
                    print(_MSG_STOP_MAX_ITER)
                break

        self._endRun()


class CpMdpValueIterationGS(CpMdpValueIteration):

    def __init__(self, shape, terminals, obstacles, succ_s, probability_s, R, states, discount, epsilon=0.01, max_iter=10, initial_value=0):
        # Initialise a value iteration Gauss-Seidel MDP.

        MDP.__init__(self, shape, terminals, obstacles, succ_s, probability_s, R, states, discount, epsilon, max_iter)
        self.iterations_list = []
        self.v_list = []
        # initialization of optional arguments
        if initial_value == 0:
            self.V = _np.zeros(self.states)

        else:
            if len(initial_value) != self.states:
                raise ValueError("The initial value must be a vector of "
                                 "length S.")
            else:
                try:
                    self.V = initial_value.reshape(self.states)  # reshape(self.S)
                except AttributeError:
                    self.V = _np.array(initial_value)
                except:
                    raise
        if self.discount < 1:
            # compute a bound for the number of iterations and update the
            # stored value of self.max_iter
            self._boundIter(epsilon)
            # computation of threshold of variation for V for an epsilon-
            # optimal policy
            self.thresh = epsilon * (1 - self.discount) / self.discount

        else:  # discount == 1
            # threshold of variation for V for an epsilon-optimal policy
            self.thresh = epsilon

    def run(self):
        # Run the value iteration Gauss-Seidel algorithm.

        self._startRun()
        self.v_list.append(self.V.copy())

        while True:
            self.iter += 1

            Vprev = self.V.copy()

            for s1 in range(len(self.split_succ_s[0])):

                Q = [float(self.R[a][s1] + self.discount * _np.dot(
                            self.split_probability[a][s1], self.V[self.split_succ_s[a][s1]]))
                    for a in range(self.A)]

                self.V[s1] = max(Q)

            variation = getSpan(self.V - Vprev)
            self.iterations_list.append(variation)
            self.v_list.append(self.V.copy())
            if self.verbose:
                _printVerbosity(self.iter, variation)

            if variation < self.thresh:
                if self.verbose:
                    print(_MSG_STOP_EPSILON_OPTIMAL_POLICY)
                break
            elif self.iter == self.max_iter:
                if self.verbose:
                    print(_MSG_STOP_MAX_ITER)
                break

        self.policy = []
        for s1 in range(len(self.split_succ_s[0])):
            Q = _np.zeros(self.A)
            for a in range(self.A):
                Q[a] = self.R[a][s1] + self.discount * _np.dot(
                    self.split_probability[a][s1], self.V[self.split_succ_s[a][s1]])

            self.V[s1] = Q.max()

            # Print utilities:
            # print(self.V[s1])

            self.policy.append(int(Q.argmax()))

        self._endRun()
