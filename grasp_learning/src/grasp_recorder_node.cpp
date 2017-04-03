#include <grasp_learning/grasp_recorder.h>

int main(int argc, char **argv) {

  using hiqp::grasp_learner::grasp_recorder;
  
  ros::init(argc,argv,"grasp_recorder_node");
  
  ros::NodeHandle nh;

  grasp_recorder Recorder;

  Recorder.addSubscription<grasp_learning::StartRecording>(nh, "/start_recording",1);
  Recorder.addSubscription<grasp_learning::FinishRecording>(nh, "/finish_recording",1);
  Recorder.addSubscription<hiqp_msgs::TaskMeasures>(nh, "/yumi/hiqp_joint_velocity_controller/task_measures",2000);
  Recorder.addSubscription<sensor_msgs::JointState>(nh, "/yumi/joint_states",2000);

  ros::AsyncSpinner spinner(4); // Use 4 threads
  spinner.start();
  ros::waitForShutdown();
  
  return 0;
}
