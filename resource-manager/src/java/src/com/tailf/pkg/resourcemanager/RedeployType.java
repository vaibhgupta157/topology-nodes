package com.tailf.pkg.resourcemanager;

public enum RedeployType {
    DEFAULT("default"),
    TOUCH("touch"),
    REDEPLOY("re-deploy"),
    REACTIVE_REDEPLOY("reactive-re-deploy");

    private final String token;
    private RedeployType(String token) {
        this.token = token;
    }

    public String getToken() {
        return this.token;
    }

    public static RedeployType from(String type){
        if (type == null) {
            return DEFAULT;
        }

        for (RedeployType rt: RedeployType.values()) {
            if (rt.token.equals(type)) {
                return rt;
            }
        }

        return DEFAULT;
    }
}