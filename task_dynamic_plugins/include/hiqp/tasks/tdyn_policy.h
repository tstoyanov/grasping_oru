// The HiQP Control Framework, an optimal control framework targeted at robotics
// Copyright (C) 2016 Marcus A Johansson
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

#ifndef HIQP_TDYN_POLICY_H
#define HIQP_TDYN_POLICY_H

#include <hiqp/robot_state.h>
#include <hiqp/task_dynamics.h>
#include <ros/ros.h>
#include "std_msgs/String.h"
#include <pluginlib/class_loader.h>
#include <grasp_learning/QueryNN.h>
#include <std_msgs/Float64MultiArray.h>

namespace hiqp
{
namespace tasks
{

  /*! \brief A general first-order task dynamics implementation that enforces an exponential decay of the task performance value.
   *  \author Marcus A Johansson */  
  class TDynPolicy : public TaskDynamics {
  public:

    inline TDynPolicy() : TaskDynamics() {}
    
    TDynPolicy(std::shared_ptr<GeometricPrimitiveMap> geom_prim_map,
                       std::shared_ptr<Visualizer> visualizer);

    ~TDynPolicy() noexcept {}

    int init(const std::vector<std::string>& parameters,
             RobotStatePtr robot_state,
             const Eigen::VectorXd& e_initial,
             const Eigen::VectorXd& e_final);

    int update(RobotStatePtr robot_state,
               const Eigen::VectorXd& e,
               const Eigen::MatrixXd& J);

    int monitor();

  private:
    TDynPolicy(const TDynPolicy& other) = delete;
    TDynPolicy(TDynPolicy&& other) = delete;
    TDynPolicy& operator=(const TDynPolicy& other) = delete;
    TDynPolicy& operator=(TDynPolicy&& other) noexcept = delete;

    std::default_random_engine generator;
    std::normal_distribution<double> dist;
    ros::Publisher starting_pub_;
    std_msgs::String msg_;
    ros::ServiceClient client_NN_;
    ros::Time t;
    ros::NodeHandle nh_;
  };

} // namespace tasks

} // namespace hiqp

#endif // include guard