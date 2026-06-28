# TaijiSkills

用自然语言管理腾讯太极 GPU 集群任务的 Claude Code Skill。

## 前置条件

```bash
export TOKEN=<your_taiji_token>
```

## 交互示例

一句话完成：查资源 → 选最优资源池 → 提交任务。

---

<h3>🖥️ 输入</h3>

```
/taiji 帮我看一下现在有哪些空的资源，然后挑一个最空闲的申请一个8卡任务，用t2m3镜像，不跑程序先占着
```

<h3>📋 输出</h3>

<h4>1. 自动查询所有资源池</h4>

<table>
<tr>
  <th>资源池</th><th>GPU</th><th align="right">配额</th><th align="right">已用</th><th align="right">空闲</th>
</tr>
<tr>
  <td><code>AILab_DHC_DD</code></td><td>V100</td><td align="right">491</td><td align="right">481</td>
  <td align="right"><b style="color:#22863a;">10 ✓</b></td>
</tr>
<tr>
  <td><code>AILab_DHC_DD</code></td><td>A100</td><td align="right">66</td><td align="right">65</td>
  <td align="right"><span style="color:#b08800;">1</span></td>
</tr>
<tr>
  <td><code>TaiJi_HYAide_MMD_DHC_A1</code></td><td>H20</td><td align="right">64</td><td align="right">64</td>
  <td align="right"><span style="color:#cb2431;">0</span></td>
</tr>
<tr>
  <td><code>AILab_DHA</code></td><td>-</td><td align="right" colspan="3"><span style="color:#959da5;">无配额</span></td>
</tr>
<tr>
  <td><code>AILab_DHC_DC</code></td><td>-</td><td align="right" colspan="3"><span style="color:#959da5;">无配额</span></td>
</tr>
</table>

> 最空闲的是 **AILab_DHC_DD**，有 10 张空闲 V100，足够申请 8 卡任务。

<h4>2. 询问任务名称</h4>

<pre>
任务名称用什么？  <b style="color:#0366d6;">[hold]</b>  [debug]  [dev]  [Other]
</pre>

<h4>3. 自动提交任务</h4>

<pre>
Task Configuration:
  Name:          hold
  GPU:           <span style="color:#6f42c1;">V100 x 8</span> (hosts: 1)
  Docker:        mirrors.tencent.com/jeffryli/tlinux3.2-python3.10-cuda11.8:v0.3
  Business:      AILab_DHC_DD
  Command:       sleep infinity
  Task Flag:     hold-V100-1x8-1437
</pre>

<pre style="background-color:#f0fff0;">
<span style="color:#22863a;">✔ Task submitted successfully!</span>
  task_flag:   <b>hold-V100-1x8-1437</b>
  instance_id: <b>8b1d81c49cb2fcf8019cc1dd719e07f6</b>
</pre>

<h4>4. 返回登录命令</h4>

```bash
taiji_client exec hold-V100-1x8-1437 8b1d81c49cb2fcf8019cc1dd719e07f6 bash
```

---

## 更多用法

```bash
/taiji 看看我的任务                     # 查看运行中的任务
/taiji 停止 hold-V100-1x8-1437         # 停止任务（会先确认）
/taiji 查看历史                         # 查看提交记录
/taiji 查一下 AILab_DHC_DD 的资源       # 查指定资源池
```
