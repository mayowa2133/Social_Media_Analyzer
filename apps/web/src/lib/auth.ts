import { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";

export const authOptions: NextAuthOptions = {
    providers: [
        GoogleProvider({
            clientId: process.env.GOOGLE_CLIENT_ID || "",
            clientSecret: process.env.GOOGLE_CLIENT_SECRET || "",
            authorization: {
                params: {
                    scope: "openid email profile https://www.googleapis.com/auth/youtube.readonly",
                    access_type: "offline",
                    prompt: "consent",
                },
            },
        }),
    ],
    callbacks: {
        async jwt({ token, account }) {
            // Persist OAuth tokens in the JWT
            if (account) {
                token.accessToken = account.access_token;
                token.refreshToken = account.refresh_token;
                token.expiresAt = account.expires_at;
                token.provider = account.provider;
            }
            return token;
        },
        async session({ session, token }) {
            // Send properties to the client
            session.accessToken = token.accessToken as string;
            session.refreshToken = token.refreshToken as string | undefined;
            session.expiresAt = token.expiresAt as number | undefined;
            session.provider = token.provider as string;
            return session;
        },
    },
    pages: {
        signIn: "/connect",
    },
    session: {
        strategy: "jwt",
    },
    secret: process.env.NEXTAUTH_SECRET,
};
