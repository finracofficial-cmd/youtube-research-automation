import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
// 静止画中心の構成なので、動きの少ないフレームを潰しすぎないようにする
Config.setCrf(20);
