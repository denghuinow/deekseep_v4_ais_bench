# aisbench_auto_tools
简化 aisbench 性能测试操作，避免手工表生成、替换性能测试数据集

### 前置操作
1. 安装aisbench（aisbench已集成在mindie镜像中，如果使用mindie镜像，可以跳过该步骤）
   ```shell
   # 详细安装步骤可参考：https://wiki.huawei.com/domains/52290/wiki/212185/WIKI202505266940138
   git clone https://gitee.com/aisbench/benchmark.git
   cd benchmark/
   pip3 install -e ./
   pip3 install -r requirements/api.txt
   ```
2. 提前创建好用于存放数据集文件夹
   ```shell
   mkdir -p /mnt/path_to_store_dataset
   ```

### 脚本实现原理
    1. 创建数据集
    2. 数据集到aisbench/gsm8k数据集目录下
    3. 通过字符串替换修改aisbench请求配置文件
    4. 执行性能测试

### 可输入参数
| 参数名                         |                   解释                    |  默认值   |
|-----------------------------|:---------------------------------------:|:------:|
| --input_len INPUT_LEN       |                  输入长度                   |  3500  |
| --output_len OUTPUT_LEN     |                  输出长度                   |  1500  |
| --data_num DATA_NUM         |                  数据集条数                  |  8192  |
| --concurrency CONCURRENCY   |               aisbench并发数               |  2048  |
| --request_rate REQUEST_RATE |            发送频率，默认为0，表示按并发发送            |   0    |
| --test_type TEST_TYPE       |  指定流式或非流式，可选值为 text 或 stream，默认为stream  | stream |
| --dataset DATASET_PATH      |      指定性能数据集路径，不传参表示默认通过gsm8k数据集生成      |  none  |
| --enable_think             | 测试 deepseek v3.1 时用于开启think功能，其他权重不需要配置 | False  |
| --test_accuracy             |    评估数据集输出精度，不直接输出精度结果，需要通过人工观察输出内容     | False  |

### 准备脚本
1. 点击右上角的`克隆/下载`将仓库 tar 包下载并上传到 linux 环境中
2. 传输到环境中并解压（如使用容器安装aisbench，请在容器中操作）
   ```shell
   tar -xvf aisbench_auto_tools-master.tar
   cd aisbench_auto_tools-master
   ```
3. 在`config.py`指定中基础配置，具体释义见代码内备注，其他文件无须进行修改
    ```python
    # 数据集文件夹, 需要提前创建, 用于生成、存放数据集, 建议创建独立的文件夹仅用于存放数据集
    DATASET_PATH = "/mnt/path_to_store_dataset"
    # aisbench 工作路径, 为 git clone aisbench 后得到的 benchmark 目录的绝对路径
    # 该路径可通过命令 `pip show ais-bench-benchmark | grep location -i` 查询
    # 如果使用mindie镜像, 则无需修改该配置项
    WORK_PATH = "/usr/local/lib/python3.11/site-packages"
    # 服务化配置的模型名称
    MODEL_NAME = "ds_r1"
    # 模型权重路径, 用于读取 tokenizer
    MODEL_PATH = "/mnt/weight/DeepSeek-R1_w8a8_mtp"
    # 请求目的 IP
    HOST_IP = "141.1.1.101"
    # 请求目的端口
    HOST_PORT = "31015"
    ```

### 执行性能测试
1. 使用流式接口测试`[3.5k,1.5k]`性能，使用 15360 条数据集，并发设置为 1536，请求频率设置为 5
   ```shell
   python3 aisbench_test.py --input_len 3500 --output_len 1500 --data_num 15360 --concurrency 1536 --request_rate 4
   ```
2. 使用流式接口**指定数据集路径**测试性能，输出长度为 2000，并发设置为 1024，按并发发送（即不配置请求频率）
   ```shell
   python3 aisbench_test.py --dataset "/mnt/path_to_dataset/dataset_7000.jsonl" --output_len 2000 --concurrency 1024
   ```
3. 使用非流式接口（该接口暂不支持统计时延数据）测试`[2k,2k]`性能，使用 640 条数据集，并发设置为 64，请求频率设置为 20
   ```shell
   python3 aisbench_test.py --input_len 2048 --output_len 2048 --data_num 640 --concurrency 64 --request_rate 20 --test_type text
   ```
4. 使用流式接口测试**指定数据集路径**的精度，输出最大长度为 1024，并发设置为 16，并发设置为 64，请求频率设置为 4
   ```shell
   python3 aisbench_test.py --dataset "/mnt/path_to_dataset/precision_dataset.jsonl" --output_len 1024 --concurrency 64 --request_rate 4 --test_accuracy
   ```
   测试结束后，不会输出精度数据，可在`./outputs/default/{time_stamp}/predictions/vllm-api-stream-chat/gsm8k.json`路径下人工评估输出内容
5. 测试模型为 `deepseek v3.1`，使用流式接口测试`[3.5k,1.5k]`性能，使用 15360 条数据集，并发设置为 1536，请求频率设置为 5
   ```shell
   # 开启思考模式
   python3 aisbench_test.py --input_len 3500 --output_len 1500 --data_num 15360 --concurrency 1536 --request_rate 4 --enable_think
   # 不开启思考模式
   python3 aisbench_test.py --input_len 3500 --output_len 1500 --data_num 15360 --concurrency 1536 --request_rate 4
   ```