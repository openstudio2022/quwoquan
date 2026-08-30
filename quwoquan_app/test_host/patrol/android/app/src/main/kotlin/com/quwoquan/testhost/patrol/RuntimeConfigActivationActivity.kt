package com.quwoquan.testhost.patrol

import android.app.Activity
import android.os.Bundle
import android.util.Log
import com.quwoquan.quwoquan_app.RuntimeConfigActivationGateway

/**
 * UAT 宿主的 activation 入口，与生产同构的两阶段冷启动中的第一阶段：编排方先用带 request
 * digest 的专用冷启动激活 runtime config，再让 Patrol 正常启动宿主进入 Flutter。
 *
 * 验签、CAS、落盘与回执全部走共编译自生产源树的 RuntimeConfigActivationGateway；gateway
 * 只暴露不可变结果，内部 store/coordinator 仍保持 package-private。本壳只负责「消费一次请求
 * 后立即结束」——生产壳还要接 launch screen、启动健康与 Flutter 引擎，宿主不需要那些，
 * 因此壳不同而语义同源。
 *
 * 判否不在此处呈现终态：编排方以「回执未在超时内出现」判否，与生产 canonical executor 的
 * 判否口径一致。
 */
class RuntimeConfigActivationActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val activation =
            RuntimeConfigActivationGateway.create(applicationContext)
                .consumePendingRequest(intent, isTaskRoot)
        when (activation.kind()) {
            RuntimeConfigActivationGateway.ResultKind.ACTIVATED ->
                Log.i(STARTUP_TAG, "uat_host_runtime_config_activation_complete")
            RuntimeConfigActivationGateway.ResultKind.FAILED ->
                Log.e(
                    STARTUP_TAG,
                    "uat_host_runtime_config_activation_failed code=" +
                        activation.errorCode() +
                        " issues=" +
                        activation.validationIssues().joinToString(","),
                )
            RuntimeConfigActivationGateway.ResultKind.NOT_REQUESTED ->
                Log.e(
                    STARTUP_TAG,
                    "uat_host_runtime_config_activation_not_requested",
                )
        }
        finishAndRemoveTask()
    }

    private companion object {
        const val STARTUP_TAG = "QWQStartup"
    }
}
